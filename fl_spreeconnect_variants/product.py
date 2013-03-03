# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2013 Factor Libre.
#
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
from base_external_referentials.decorator import only_for_referential, catch_error_in_report, open_report

class product_template(osv.osv):
    _inherit = 'product.template'

    @only_for_referential('spree')
    def _record_external_resources(self, cr, uid, external_session, resources, defaults=None, mapping=None, mapping_id=None, context=None):
        """Abstract function to record external resources (this will convert the data and create/update the object in openerp)

        :param ExternalSession external_session : External_session that contain all params of connection
        :param list resource: list of resource to import
        :param dict defaults: default value for the resource to create
        :param dict mapping: dictionnary of mapping, the key is the mapping id
        :param int mapping_id: mapping id
        :rtype: dict
        :return: dictionary with the key "create_ids" and "write_ids" which containt the id created/written
        """
        if context is None: context = {}
        result = {'write_ids': [], 'create_ids': []}
        mapping, mapping_id = self._init_mapping(cr, uid, external_session.referential_id.id, mapping=mapping, mapping_id=mapping_id, context=context)
        if mapping[mapping_id]['key_for_external_id']:
            context['external_id_key_for_report'] = mapping[mapping_id]['key_for_external_id']
        else:
            for field in mapping[mapping_id]['mapping_lines']:
                if field['alternative_key']:
                    context['external_id_key_for_report'] = field['external_field']
                    break
        for resource in resources:
            res = self._record_one_external_resource(cr, uid, external_session, resource, defaults=defaults, mapping=mapping, mapping_id=mapping_id, context=context)
            if res:
                if res.get('create_id'): result['create_ids'].append(res['create_id'])
                if res.get('write_id'): result['write_ids'].append(res['write_id'])
        return result

product_template()
