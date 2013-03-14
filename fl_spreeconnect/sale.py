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
from base_external_referentials.external_osv import ExternalSession

class sale_shop(osv.osv):
    _inherit = 'sale.shop'

    def import_inventory(self, cr, uid, ids, context=None):
        #TODO: To do function to import inventory on single products.
        return True

sale_shop()

class sale_order(osv.osv):
  _inherit = 'sale.order'

    @only_for_referential('spree')
    def _get_filter(self, cr, uid, external_session, page, previous_filter=None, context=None):
        params = {}
        if page:
            params['page'] = page
            params['q[completed_at_present]'] = "1"
            params['q[state_not_eq]'] = 'cancel'
        return params

    @only_for_referential('spree')   
    def _import_resources(self, cr, uid, external_session, defaults=None, context=None):
        external_session.logger.info("Start to import the ressource %s"%(self._name,))
        result = {"create_ids" : [], "write_ids" : []}
        mapping, mapping_id = self._init_mapping(cr, uid, external_session.referential_id.id, context=context)

        if mapping[mapping_id].get('mapping_lines', False):
            external_resource_name = mapping[mapping_id]['external_resource_name']
            resource_filter = None
            page = 1
            #paginated results in spree
            resource_filter = self._get_filter(cr, uid, external_session, page, previous_filter=resource_filter, context=context)
            order_list = self.call_spree_method(cr, uid, external_session, "orders", method="GET", params=resource_filter, context=context)
            total_pages = order_list.get('pages',1)
            order_numbers = map(lambda o: o['number'], order_list['orders'])

            while page < total_pages:
                page += 1
                resource_filter = self._get_filter(cr, uid, external_session, page, previous_filter=resource_filter, context=context)
                order_list = self.call_spree_method(cr, uid, external_session, "orders", method="GET", params=resource_filter, context=context)
                order_numbers += map(lambda o: o['number'], order_list['orders'])

            for number in order_numbers:
                order_resource = self.call_spree_method(cr, uid, external_session, "orders/%s" % number, method="GET", context=context)
                res = self._record_external_resources(cr, uid, external_session, [order_resource], defaults=defaults, mapping=mapping, mapping_id=mapping_id, context=context)
                for key in result:
                    result[key].append(res.get(key, []))
    return result
                

sale_order()