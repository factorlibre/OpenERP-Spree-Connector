# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2013 Factor Libre.
#    Author:
#        Hugo Santos <hugo.santos@factorlibre.com>
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from osv import osv, fields
from tools.translate import _
from openerp.tools.config import config

from base_external_referentials.decorator import only_for_referential
from base_external_referentials.external_referentials import REF_VISIBLE_FIELDS
from base_external_referentials.external_osv import ExternalSession
from .spree_osv import Connection

import requests
from datetime import datetime

REF_VISIBLE_FIELDS['Spree'] = ['location', 'apipass']

class external_referential(osv.osv):
    _inherit = "external.referential"

    _lang_support = 'fields_with_main_lang'

    _columns = {
        'last_product_import_date': fields.datetime('Date of last product import', readonly=True)
    }

    @only_for_referential('spree')
    def external_connection(self, cr, uid, id, debug=False, logger=False, context=None):
        if isinstance(id, list):
            id=id[0]
        referential = self.browse(cr, uid, id, context=context)
        attr_conn = Connection(referential.location, referential.apipass, debug, logger)
        return attr_conn or False

    @only_for_referential('spree')
    def product_category_import(self, cr, uid, ids, context=None):
        self.import_resources(cr, uid, ids, 'product.category', method='search_read_no_loop', context=context)
        return True

    @only_for_referential('spree')
    def product_import(self, cr, uid, ids, context=None):
        self.import_resources(cr, uid, ids, 'product.template', method='search_then_read', context=context)
        self.write(cr, uid, ids, {'last_product_import_date': datetime.now()})
        return True

    @only_for_referential('spree')
    def image_import(self, cr, uid, ids, context=None):
        self.import_resources(cr, uid, ids, 'product.images', context=context)
        return True

    def _compare_countries(self, cr, uid, spree_field, oe_field, spree_dict, oe_dict, context=None):
        if oe_dict[oe_field] == spree_dict[spree_field]:
            return True
        return False

    def _compare_taxes(self, cr, uid, spree_field, oe_field, spree_dict, oe_dict, context=None):
        if oe_dict['type_tax_use'] == 'sale'\
                    and abs(oe_dict[oe_field] - float(spree_dict[spree_field]))<0.01:
            return True
        else:
            return False

    #Based on _bidirectional_synchro in prestashoperpconnect by Akretion
    #https://launchpad.net/prestashoperpconnect
    def _bidirectional_synchro(self, cr, uid, external_session, obj_readable_name, oe_obj, spree_field, spree_readable_field, oe_field, oe_readable_field, compare_function, context=None):
        external_session.logger.info(_("[%s] Starting synchro between OERP and Spree") %obj_readable_name)
        referential_id = external_session.referential_id.id
        nr_sp_already_mapped = 0
        nr_sp_mapped = 0
        nr_sp_not_mapped = 0
        # Get all OERP obj
        oe_ids = oe_obj.search(cr, uid, [], context=context)
        fields_to_read = [oe_field]
        if not oe_readable_field == oe_field:
            fields_to_read.append(oe_readable_field)
        oe_list_dict = oe_obj.read(cr, uid, oe_ids, fields_to_read, context=context)
        #print "oe_list_dict=", oe_list_dict

        ext_resources = oe_obj._get_external_resources_complete(cr, uid, external_session, context=context)
        ext_resources_list = []
        if isinstance(ext_resources, list):
            ext_resources_list = ext_resources
        elif isinstance(ext_resources, dict):
            if ext_resources.get('pages'):
                total_pages = ext_resources['pages']
                page = 1
                oe_mapping = oe_obj._get_mapping(cr, uid, external_session.referential_id.id, context=context)
                external_resource_name = oe_mapping['external_resource_name']
                while page < total_pages:
                    ext_resources_list += ext_resources.get(external_resource_name, [])
                    page += 1
                    ext_resources = oe_obj._get_external_resources_complete(cr, uid, external_session, resource_filter={'page': page}, context=context)
        else:
            ext_resources_list.append(ext_resources)

        for spree_dict in ext_resources_list:
            # Check if the SP ID is already mapped to an OE ID
            sp_id = spree_dict.get('id')
            oe_id = oe_obj.extid_to_existing_oeid(cr, uid, external_id=sp_id, referential_id=referential_id, context=context)
            #print "oe_c_id=", oe_id
            if oe_id:
                # Do nothing for the SP IDs that are already mapped
                external_session.logger.debug(_("[%s] Spree ID %s is already mapped to OERP ID %s") %(obj_readable_name, sp_id, oe_id))
                nr_sp_already_mapped += 1
            else:
                mapping_found = False
                # Loop on OE IDs
                for oe_dict in oe_list_dict:
                    # Search for a match
                    if compare_function(cr, uid, spree_field, oe_field, spree_dict, oe_dict, context=context):
                        # it matches, so I write the external ID
                        oe_obj.create_external_id_vals(cr, uid, existing_rec_id=oe_dict['id'], external_id=sp_id, referential_id=referential_id, context=context)
                        external_session.logger.info(
                            _("[%s] Mapping Spree '%s' (%s) to OERP '%s' (%s)")
                            % (obj_readable_name, spree_dict[spree_readable_field], spree_dict[spree_field], oe_dict[oe_readable_field], oe_dict[oe_field]))
                        nr_sp_mapped += 1
                        mapping_found = True
                        break
                if not mapping_found:
                    # if it doesn't match, I just print a warning
                    external_session.logger.warning(
                        _("[%s] Spree '%s' (%s) was not mapped to any OERP entry")
                        % (obj_readable_name, spree_dict[0][spree_readable_field], spree_dict[0][spree_field]))
                    nr_sp_not_mapped += 1
        external_session.logger.info(
            _("[%s] Synchro between OERP and Spree successfull") %obj_readable_name)
        external_session.logger.info(_("[%s] Number of Spree entries already mapped = %s")
            % (obj_readable_name, nr_sp_already_mapped))
        external_session.logger.info(_("[%s] Number of Spree entries mapped = %s")
            % (obj_readable_name, nr_sp_mapped))
        external_session.logger.info(_("[%s] Number of Spree entries not mapped = %s")
            % (obj_readable_name, nr_sp_not_mapped))
        return True

    @only_for_referential('spree')
    def import_base_objects(self, cr, uid, ids, context=None):
        cur_referential = self.browse(cr, uid, ids[0], context=context)
        external_session = ExternalSession(cur_referential)

        self._bidirectional_synchro(cr, uid, external_session, obj_readable_name='TAXES',
            oe_obj=self.pool.get('account.tax'),
            spree_field='amount', spree_readable_field='name',
            oe_field='amount',
            oe_readable_field='type_tax_use',
            compare_function=self._compare_taxes, context=context)

        self._bidirectional_synchro(cr, uid, external_session, obj_readable_name='COUNTRIES',
            oe_obj=self.pool.get('res.country'),
            spree_field='iso', spree_readable_field='name',
            oe_field='code',
            oe_readable_field='name',
            compare_function=self._compare_countries, context=context)

        self.import_resources(cr, uid, ids, 'payment.method', method='search_read_no_loop', context=context)

        return True


external_referential()