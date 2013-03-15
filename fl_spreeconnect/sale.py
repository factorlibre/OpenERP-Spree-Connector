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
from openerp.osv.orm import Model
from tools.translate import _
from base_external_referentials.external_osv import ExternalSession, override
from base_external_referentials.decorator import only_for_referential

class sale_shop(Model):
    _inherit = 'sale.shop'

    def import_inventory(self, cr, uid, ids, context=None):
        #TODO: To do function to import inventory on single products.
        return True

    def import_orders(self, cr, uid, ids, context=None):
        shop = self.browse(cr, uid, ids[0])
        print "MCD"
        print "REFERENTIAL %s" % shop.referential_id
        self.import_resources(cr, uid, ids, 'sale.order', context=context)
        return True

    def import_resources(self, cr, uid, ids, resource_name, context=None):
        """Abstract function to import resources from a shop / a referential...

        :param list ids: list of id
        :param str ressource_name: the resource name to import
        :param str method: method used for importing the resource (search_then_read,
                                search_then_read_no_loop, search_read, search_read_no_loop )
        :rtype: dict
        :return: dictionary with the key "create_ids" and "write_ids" which containt the id created/written
        """
        if context is None: context={}
        result = {"create_ids" : [], "write_ids" : []}
        for browse_record in self.browse(cr, uid, ids, context=context):
            if browse_record._name == 'external.referential':
                external_session = ExternalSession(browse_record, browse_record)
            else:
                if hasattr(browse_record, 'referential_id'):
                    context['%s_id'%browse_record._name.replace('.', '_')] = browse_record.id
                    external_session = ExternalSession(browse_record.referential_id, browse_record)
                else:
                    raise except_osv(_("Not Implemented"),
                                         _("The field referential_id doesn't exist on the object %s. Reporting system can not be used") % (browse_record._name,))
            defaults = self.pool.get(resource_name)._get_default_import_values(cr, uid, external_session, context=context)
            res = self.pool.get(resource_name)._import_resources(cr, uid, external_session, defaults, context=context)
            for key in result:
                result[key].append(res.get(key, []))
        return result

sale_shop()

class sale_order(Model):
    _inherit = 'sale.order'

    @only_for_referential('spree')
    def _get_filter(self, cr, uid, external_session, page, previous_filter=None, context=None):
        params = {}
        if page:
            params['page'] = page
            params['q[state_eq]'] = "complete"
        return params

    def _convert_special_fields(self, cr, uid, vals, referential_id, context=None):
        #TODO
        return vals

    def _import_resources(self, cr, uid, external_session, defaults=None, context=None):
        partner_pool = self.pool.get('res.partner')
        partner_address_pool = self.pool.get('res.partner.address')

        external_session.logger.info("Start to import the ressource %s"%(self._name,))
        result = {"create_ids" : [], "write_ids" : []}
        mapping, mapping_id = self._init_mapping(cr, uid, external_session.referential_id.id, context=context)
        partner_mapping, partner_mapping_id = partner_pool._init_mapping(cr, uid, external_session.referential_id.id, context=context)
        partner_address_mapping, partner_address_mapping_id = partner_address_pool._init_mapping(cr, uid, external_session.referential_id.id, context=context)

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
                partner_data = {}
                order_resource = self.call_spree_method(cr, uid, external_session, "orders/%s" % number, method="GET", context=context)
                #Sync partner
                order_resource['partner_id'] = None
                if partner_mapping[partner_mapping_id].get('mapping_lines',False) and \
                  order_resource.get('email') and order_resource.get('user_id'):
                    partner_data = {'email': order_resource.get('email'), 'user_id': order_resource.get('user_id')}
                    partner_res = partner_pool._record_external_resources(cr, uid, external_session, [partner_data], 
                        mapping=partner_mapping, mapping_id=partner_mapping_id, context=context)
                    order_resource['partner_id'] = order_resource.get('user_id')

                #Set partner_id and type in bill_address and ship_address
                if order_resource.get('bill_address'):
                    order_resource['bill_address']['partner_id'] = order_resource['partner_id']
                    order_resource['bill_address']['type'] = 'invoice'
                    order_resource['bill_address_id'] = order_resource['bill_address']['id']
                    partner_address_pool._record_external_resources(cr, uid, external_session, [order_resource['bill_address']],
                        mapping=partner_address_mapping, mapping_id=partner_address_mapping_id, context=context)

                if order_resource.get('ship_address'):
                    order_resource['ship_address']['partner_id'] = order_resource['partner_id']
                    order_resource['ship_address']['type'] = 'delivery'
                    order_resource['ship_address_id'] = order_resource['ship_address']['id']
                    partner_address_pool._record_external_resources(cr, uid, external_session, [order_resource['ship_address']],
                        mapping=partner_address_mapping, mapping_id=partner_address_mapping_id, context=context)
                
                order_resource['order_line'] = []
                print external_session
                res = self._record_external_resources(cr, uid, external_session, [order_resource], defaults=defaults, mapping=mapping, mapping_id=mapping_id, context=context)
                for key in result:
                    result[key].append(res.get(key, []))
        return result

    
    def _merge_with_default_values(self, cr, uid, external_session, ressource, vals, sub_mapping_list, defaults=None, context=None):
        # if vals.get('name'):
        #     shop = external_session.sync_from_object
        #     if shop.order_prefix:
        #         vals['name'] = '%s%s' %(shop.order_prefix, vals['name'])
        if context is None: context ={}
        if vals.get('payment_method_id'):
            payment_method = self.pool.get('payment.method').browse(cr, uid, vals['payment_method_id'], context=context)
            workflow_process = payment_method.workflow_process_id
            if workflow_process:
                vals['order_policy'] = workflow_process.order_policy
                vals['picking_policy'] = workflow_process.picking_policy
                vals['invoice_quantity'] = workflow_process.invoice_quantity
        # update vals with order onchange in order to compute taxes
        vals = self.play_sale_order_onchange(cr, uid, vals, defaults=defaults, context=context)
        return super(sale_order, self)._merge_with_default_values(cr, uid, external_session, ressource, vals, sub_mapping_list, defaults=defaults, context=context)
                

sale_order()