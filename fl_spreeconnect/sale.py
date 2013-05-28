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

from datetime import datetime

from osv import osv, fields
from openerp.osv.orm import Model
from tools.translate import _
from base_external_referentials.external_osv import ExternalSession, override
from base_external_referentials.decorator import only_for_referential
import netsvc

class sale_shop(Model):
    _inherit = 'sale.shop'

    def import_inventory(self, cr, uid, ids, context=None):
        if context is None:
            context = {}

        for shop in self.browse(cr, uid, ids, context=context):
            inventory_pool = self.pool.get('stock.inventory')
            inventory_line_pool = self.pool.get('stock.inventory.line')
            product_pool = self.pool.get('product.product')

            if not shop.referential_id:
                raise osv.except_osv(_('Error!'),_('You have to define an external referential in the shop in order to import the inventory'))
            
            inventory_date = datetime.now()
            inventory_id = inventory_pool.create(cr, uid, 
                {'date': inventory_date,
                 'company_id': shop.company_id.id,
                 'name': "Spree Inventory: %s" % (inventory_date)
            })

            external_session = ExternalSession(shop.referential_id)
            products = external_session.connection.call('products')
            page = 1
            total_pages = isinstance(products, dict) and products.get('pages', 1) or 1
            while page <= total_pages:
                for product in products['products']:
                    if product.get('variants'):
                        for variant in product['variants']:
                            if variant['count_on_hand'] != 0:
                                erp_product_id = product_pool.get_oeid(cr, uid, variant['id'], shop.referential_id.id, context=context)
                                if not erp_product_id:
                                    _logger.warning("External Variant %s not found. Please import products before import inventory" % variant['id'])
                                    continue
                                erp_product = product_pool.browse(cr, uid, erp_product_id, context=context)
                                inv_val = {
                                    'company_id': shop.company_id.id,
                                    'inventory_id': inventory_id,
                                    'location_id': shop.warehouse_id and shop.warehouse_id.lot_stock_id.id,
                                    'product_id': erp_product.id,
                                    'product_uom': erp_product.uom_id.id,
                                    'product_qty': variant['count_on_hand']
                                }
                                inventory_line = inventory_line_pool.create(cr, uid, inv_val)
                                _logger.info("Created inventory line for external product %s and openerp product %s with qty %s" % (variant['id'], erp_product_id, variant['count_on_hand']))
                page += 1
                products = external_session.connection.call('products', params={'page': page})
            return True

    def export_inventory(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        product_pool = self.pool.get('product.product')
        product_template_pool = self.pool.get('product.template')

        for shop in self.browse(cr, uid, ids, context=context):
            

            if not shop.referential_id:
                raise osv.except_osv(_('Error!'),_('You have to define an external referential in the shop in order to import the inventory'))

            #Update all Inventories
            context['warehouse'] = shop.warehouse_id.id
            product_ids = product_pool.search(cr, uid, [], context=context)
            external_session = ExternalSession(shop.referential_id)
            product_pool.update_spree_stock(cr, uid, product_ids, external_session, context=context)
        return True

                
    def import_orders(self, cr, uid, ids, context=None):
        ctx = dict(context)
        ctx['filter_params'] = {'q[state_eq]': 'complete'}
        self.import_resources(cr, uid, ids, 'sale.order', method='search_then_read', context=context)
        return True

    # def import_resources(self, cr, uid, ids, resource_name, context=None):
    #     """Abstract function to import resources from a shop / a referential...

    #     :param list ids: list of id
    #     :param str ressource_name: the resource name to import
    #     :param str method: method used for importing the resource (search_then_read,
    #                             search_then_read_no_loop, search_read, search_read_no_loop )
    #     :rtype: dict
    #     :return: dictionary with the key "create_ids" and "write_ids" which containt the id created/written
    #     """
    #     if context is None: context={}
    #     result = {"create_ids" : [], "write_ids" : []}
    #     for browse_record in self.browse(cr, uid, ids, context=context):
    #         if browse_record._name == 'external.referential':
    #             external_session = ExternalSession(browse_record, browse_record)
    #         else:
    #             if hasattr(browse_record, 'referential_id'):
    #                 context['%s_id'%browse_record._name.replace('.', '_')] = browse_record.id
    #                 external_session = ExternalSession(browse_record.referential_id, browse_record)
    #             else:
    #                 raise except_osv(_("Not Implemented"),
    #                                      _("The field referential_id doesn't exist on the object %s. Reporting system can not be used") % (browse_record._name,))
    #         defaults = self.pool.get(resource_name)._get_default_import_values(cr, uid, external_session, context=context)
    #         res = self.pool.get(resource_name)._import_resources(cr, uid, external_session, defaults, context=context)
    #         for key in result:
    #             result[key].append(res.get(key, []))
    #     return result

sale_shop()

class sale_order(Model):
    _inherit = 'sale.order'

    @only_for_referential('spree')
    def _get_external_resource_ids(self, cr, uid, external_session, resource_filter=None, \
            mapping=None, mapping_id=None, context=None):
        mapping, mapping_id = self._init_mapping(cr, uid, external_session.referential_id.id, mapping=mapping, mapping_id=mapping_id, context=context)
        ext_resource = mapping[mapping_id]['external_resource_name']
        list_method = mapping[mapping_id]['external_list_method']
        get_method = mapping[mapping_id]['external_get_method']

        id_field = 'number'

        if not list_method:
            if not get_method:
                raise except_osv(_('User Error'), _('There is not list method for the mapping %s')%(mapping[mapping_id]['model'],))
            else:
                #Return [None] because in Spree are models with only one record. List Method is not defined in mapping
                return [None]

        params = {'fields': 'id'}
        if resource_filter:
            params.update(resource_filter)

        res = external_session.connection.call(list_method, params=resource_filter)

        ids = []
        if res.get(list_method):
            ids = map(lambda obj: obj.get(id_field), res[list_method])

        return ids

    def _convert_special_fields(self, cr, uid, vals, referential_id, context=None):
        vals['order_line'] = vals.get('order_line', [])
        for option in self._get_special_fields(cr, uid, context=context):
            vals = self._add_order_extra_line(cr, uid, vals, option, context=context)

        return vals

    def _add_order_extra_line(self, cr, uid, vals, option, context):
        """ Add or substract amount on order as a separate line item with single quantity for each type of amounts like :
        shipping, cash on delivery, discount, gift certificates...

        :param dict vals: values of the sale order to create
        :param option: dictionnary of option for the special field to process
        """
        if context is None: context={}
        sign = option.get('sign', 1)
        if context.get('is_tax_included') and vals.get(option['price_unit_tax_included']):
            price_unit = vals.pop(option['price_unit_tax_included']) * sign
        elif vals.get(option['price_unit_tax_excluded']):
            price_unit = vals.pop(option['price_unit_tax_excluded']) * sign
        else:
            for key in ['price_unit_tax_excluded', 'price_unit_tax_included', 'tax_rate_field']:
                if option.get(key) and option[key] in vals:
                    del vals[option[key]]
            return vals #if there is not price, we have nothing to import

        model_data_obj = self.pool.get('ir.model.data')
        model, product_id = model_data_obj.get_object_reference(cr, uid, *option['product_ref'])
        product = self.pool.get('product.product').browse(cr, uid, product_id, context)

        extra_line = {
                        'product_id': product.id,
                        'name': product.name,
                        'product_uom': product.uom_id.id,
                        'product_uom_qty': 1,
                        'price_unit': price_unit,
                    }

        extra_line = self.pool.get('sale.order.line').play_sale_order_line_onchange(cr, uid, extra_line, vals, vals['order_line'], context=context)
        if context.get('use_external_tax') and option.get('tax_rate_field'):
            tax_rate = vals.get(option['tax_rate_field'])
            if tax_rate:
                del vals[option['tax_rate_field']]
                line_tax_id = self.pool.get('account.tax').get_tax_from_rate(cr, uid, tax_rate, context.get('is_tax_included'), context=context)
                if not line_tax_id:
                    raise except_osv(_('Error'), _('No tax id found for the rate %s with the tax include = %s')%(tax_rate, context.get('is_tax_included')))
                extra_line['tax_id'] = [(6, 0, [line_tax_id])]
            else:
                extra_line['tax_id'] = False
        if not option.get('tax_rate_field') and extra_line.get('tax_id'):
            del extra_line['tax_id']
        ext_code_field = option.get('code_field')
        if ext_code_field and vals.get(ext_code_field):
            extra_line['name'] = "%s [%s]" % (extra_line['name'], vals[ext_code_field])
        vals['order_line'].append((0, 0, extra_line))
        return vals

    # def _import_resources(self, cr, uid, external_session, defaults=None, context=None):
    #     if context is None: context = {}
    #     if defaults is None: defaults = {}

    #     partner_pool = self.pool.get('res.partner')
    #     partner_address_pool = self.pool.get('res.partner.address')
    #     sale_line_pool = self.pool.get('sale.order.line')

    #     external_session.logger.info("Start to import the ressource %s"%(self._name,))
    #     result = {"create_ids" : [], "write_ids" : []}
    #     mapping, mapping_id = self._init_mapping(cr, uid, external_session.referential_id.id, context=context)
    #     partner_mapping, partner_mapping_id = partner_pool._init_mapping(cr, uid, external_session.referential_id.id, context=context)
    #     partner_address_mapping, partner_address_mapping_id = partner_address_pool._init_mapping(cr, uid, external_session.referential_id.id, context=context)
    #     sale_line_mapping, sale_line_mapping_id = sale_line_pool._init_mapping(cr, uid, external_session.referential_id.id, context=context)

    #     if mapping[mapping_id].get('mapping_lines', False):
    #         external_resource_name = mapping[mapping_id]['external_resource_name']
    #         resource_filter = None
    #         page = 1
    #         #paginated results in spree
    #         resource_filter = self._get_filter(cr, uid, external_session, page, previous_filter=resource_filter, context=context)
    #         order_list = self.call_spree_method(cr, uid, external_session, "orders", method="GET", params=resource_filter, context=context)
    #         total_pages = order_list.get('pages',1)
    #         order_numbers = map(lambda o: o['number'], order_list['orders'])
            
    #         while page < total_pages:
    #             page += 1
    #             resource_filter = self._get_filter(cr, uid, external_session, page, previous_filter=resource_filter, context=context)
    #             order_list = self.call_spree_method(cr, uid, external_session, "orders", method="GET", params=resource_filter, context=context)
    #             order_numbers += map(lambda o: o['number'], order_list['orders'])

    #         for number in order_numbers:
    #             partner_data = {}
    #             order_resource = self.call_spree_method(cr, uid, external_session, "orders/%s" % number, method="GET", context=context)
    #             #Sync partner
    #             order_resource['partner_id'] = order_resource.get('user_id')
    #             if partner_mapping[partner_mapping_id].get('mapping_lines',False) and \
    #               order_resource.get('email') and order_resource.get('user_id'):
    #                 partner_data = {'email': order_resource.get('email'), 'user_id': order_resource.get('user_id')}
    #                 partner_res = partner_pool._record_external_resources(cr, uid, external_session, [partner_data], 
    #                     mapping=partner_mapping, mapping_id=partner_mapping_id, context=context)

    #             #Set partner_id and type in bill_address and ship_address
    #             if order_resource.get('bill_address'):
    #                 order_resource['bill_address']['partner_id'] = order_resource['user_id']
    #                 order_resource['bill_address']['type'] = 'invoice'
    #                 order_resource['bill_address_id'] = order_resource['bill_address']['id']
    #                 partner_address_pool._record_external_resources(cr, uid, external_session, [order_resource['bill_address']],
    #                     mapping=partner_address_mapping, mapping_id=partner_address_mapping_id, context=context)

    #             if order_resource.get('ship_address'):
    #                 order_resource['ship_address']['partner_id'] = order_resource['user_id']
    #                 order_resource['ship_address']['type'] = 'delivery'
    #                 order_resource['ship_address_id'] = order_resource['ship_address']['id']
    #                 partner_address_pool._record_external_resources(cr, uid, external_session, [order_resource['ship_address']],
    #                     mapping=partner_address_mapping, mapping_id=partner_address_mapping_id, context=context)

    #             if not context.get('is_tax_included', False) and context.get('use_external_tax'): 
    #                 #If is tax_excluded adjustments are included in Order So we have to include it in line
    #                 if order_resource.get('adjustments'):
    #                     tax_adjustments = []
    #                     for adj in order_resource.get('adjustments'):
    #                         if adj.get('adjustment') \
    #                           and adj['adjustment'].get('originator_type') == 'Spree::TaxRate':
    #                             tax_adjustments.append(adj)
    #                     for line in order_resource['line_items']:
    #                         line['adjustments'] += tax_adjustments

    #             res = self._record_external_resources(cr, uid, external_session, [order_resource], defaults=defaults, mapping=mapping, mapping_id=mapping_id, context=context)
    #             for key in result:
    #                 result[key].append(res.get(key, []))

    #     return result

sale_order()

class sale_order_line(Model):
    _inherit = 'sale.order.line'

    def play_sale_order_line_onchange(self, cr, uid, line, parent_data, previous_lines, defaults=None, context=None):
        account_tax = self.pool.get('account.tax')
        if context is None:
            context = {}
        if defaults is None:
            defaults = {}
        print line
        original_line = line.copy()
        if not context.get('use_external_tax') and 'tax_id' in line:
            del line['tax_id']
        if parent_data is None:
            parent_data = context.get('parent_data', {})

        line = self.call_onchange(cr, uid, 'product_id_change', line, defaults=defaults, parent_data=parent_data or {}, previous_lines=previous_lines or {}, context=context)
        #TODO all m2m should be mapped correctly
        if context.get('use_external_tax'):
            #if we use the external tax and the onchange have added a taxe, 
            #them we remove it.
            #Indeed we have to make the difference between a real tax_id
            #imported and a default value set by the onchange
            if 'tax_id' in line:
                del line['tax_id']

        elif line and line.get('tax_id'):
            line['tax_id'] = [(6, 0, line['tax_id'])]
        return line

    def _transform_one_resource(self, cr, uid, external_session, convertion_type, resource, mapping, mapping_id,
                     mapping_line_filter_ids=None, parent_data=None, previous_result=None, defaults=None, context=None):

        account_tax = self.pool.get('account.tax')
        if context is None: context={}

        line = super(sale_order_line, self)._transform_one_resource(cr, uid, external_session, convertion_type, resource,
                            mapping, mapping_id, mapping_line_filter_ids=mapping_line_filter_ids, parent_data=parent_data,
                            previous_result=previous_result, defaults=defaults, context=context)

        if context.get('is_tax_included') and 'price_unit_tax_included' in line:
            line['price_unit'] = line['price_unit_tax_included']
        elif 'price_unit_tax_excluded' in line:
            line['price_unit']  = line['price_unit_tax_excluded']

        line = self.play_sale_order_line_onchange(cr, uid, line, parent_data, previous_result,
                                                                        defaults, context=context)
        if context.get('use_external_tax'):
            #get adjustment from resource
            print "USE EXTERNAL TAX %s" % resource
            erp_tax_id = False
            if resource.get('adjustments'):
                for adj in resource.get('adjustments'):
                    adjustment = adj['adjustment']
                    if adjustment['originator_type'] == 'Spree::TaxRate':
                        erp_tax_id = account_tax.get_oeid(cr, uid, adjustment['originator_id'], 
                            external_session.referential_id.id, context=context)
            if erp_tax_id:
                line['tax_id'] = [(6, 0, [erp_tax_id])]
            else:
                line['tax_id'] = False
        return line

sale_order_line()