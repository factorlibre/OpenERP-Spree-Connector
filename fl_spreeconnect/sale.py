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

import time
from datetime import datetime
import dateutil.parser

from osv import osv, fields
from openerp.osv.orm import Model
from tools.translate import _
from tools import DEFAULT_SERVER_DATETIME_FORMAT, DEFAULT_SERVER_DATE_FORMAT
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
        self.import_resources(cr, uid, ids, 'sale.order', method='search_then_read', context=context)
        self.write(cr, uid, ids, {'import_orders_from_date': time.strftime(DEFAULT_SERVER_DATETIME_FORMAT)})
        return True

sale_shop()

class sale_order(Model):
    _inherit = 'sale.order'

    @only_for_referential('spree')
    def check_if_order_exist(self, cr, uid, external_session, resource, order_mapping=None, defaults=None, context=None):
        shop = external_session.sync_from_object
        order_name = '%s%s' %(shop.order_prefix, resource['number'])
        exist_id = self.search(cr, uid, [['name', '=', order_name]], context=context)
        if exist_id:
            external_session.logger.info("Sale Order %s already exist in OpenERP,"
                                            "no need to import it again"%order_name)
            return True
        return False

    def add_adjustment_line(self, cr, uid, resource, context=None):
        taxes = []
        for adj in resource.get('adjustments', []):
            if adj['originator_type'] == 'Spree::TaxRate':
                taxes.append(adj)
        for line in resource.get('line_items', []):
            line.update({'adjustments': taxes})
        return resource

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

    @only_for_referential('spree')
    def _transform_one_resource(self, cr, uid, external_session, convertion_type, resource, mapping, mapping_id, \
                     mapping_line_filter_ids=None, parent_data=None, previous_result=None, defaults=None, context=None):

        resource = self.add_adjustment_line(cr, uid, resource, context=context)

        return super(sale_order, self)._transform_one_resource(cr, uid, external_session, convertion_type, resource,\
                 mapping, mapping_id,  mapping_line_filter_ids=mapping_line_filter_ids, parent_data=parent_data,\
                 previous_result=previous_result, defaults=defaults, context=context)

    @only_for_referential('spree')
    def _merge_with_default_values(self, cr, uid, external_session, resource, vals, sub_mapping_list, defaults=None, context=None):
        address_pool = self.pool.get('res.partner.address')
        resource_partner = {'email': resource.get('email'), 'user_id': resource.get('user_id')}
        res_partner = self.pool.get('res.partner')._record_one_external_resource(cr, uid, external_session,
                resource_partner, context=context)
        vals['partner_id'] = res_partner.get('write_id') or res_partner.get('create_id')

        address_defaults = {'partner_id': vals['partner_id'] }
        address_types = {'bill_address': 'invoice', 'ship_address': 'delivery'}
        for addr_key in address_types.keys():
            if resource.get(addr_key):                
                address_id = address_pool.get_oeid(cr, uid, resource[addr_key]['id'], 
                    external_session.referential_id.id, context=context)
                if not address_id:
                    address_defaults.update({'type': address_types[addr_key]})
                    addr_res = address_pool._record_one_external_resource(cr, uid, external_session,
                        resource.get(addr_key), defaults=address_defaults, context=context)
                    address_id = addr_res.get('write_id') or addr_res.get('create_id')
                if addr_key == 'bill_address':
                    vals['partner_invoice_id'] = address_id
                else:
                    vals['partner_shipping_id'] = address_id

        return super(sale_order, self)._merge_with_default_values(cr, uid, external_session, resource, vals, sub_mapping_list, defaults=defaults, context=context)

    def _convert_special_fields(self, cr, uid, vals, referential_id, context=None):
        vals['order_line'] = vals.get('order_line', [])
        return super(sale_order, self)._convert_special_fields(cr, uid, vals, referential_id, context=context)

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
            tax_rate = vals.pop(option['tax_rate_field'])
            if tax_rate:
                line_tax_id = self.pool.get('account.tax').get_tax_from_rate(cr, uid, tax_rate, context.get('is_tax_included'), context=context)
                if not line_tax_id:
                    raise except_osv(_('Error'), _('No tax id found for the rate %s with the tax include = %s')%(tax_rate, context.get('is_tax_included')))
                extra_line['tax_id'] = [(6, 0, [line_tax_id])]
            else:
                extra_line['tax_id'] = False
        if not option.get('tax_rate_field'):
            if extra_line.get('tax_id'):
                del extra_line['tax_id']
        ext_code_field = option.get('code_field')
        if ext_code_field and vals.get(ext_code_field):
            extra_line['name'] = "%s [%s]" % (extra_line['name'], vals[ext_code_field])
        vals['order_line'].append((0, 0, extra_line))
        return vals

    @only_for_referential('spree')
    def _get_filter(self, cr, uid, external_session, step, previous_filter=None, context=None):
        order_filter = super(sale_order, self)._get_filter(cr, uid, external_session, step, 
            previous_filter=previous_filter, context=context)
        order_filter['q[state_eq]'] = 'complete'
        order_filter['q[completed_at_present'] = 1
        shop = False
        if external_session.sync_from_object._name == 'sale.shop':
            shop = external_session.sync_from_object
        elif context.get('sale_shop_id'):
            shop = self.pool.get('sale.shop').browse(cr, uid,  context['sale_shop_id'], context=context)
        # if shop and shop.import_orders_from_date:
        #     order_filter['q[completed_at_gt]'] = shop.import_orders_from_date
        return order_filter

sale_order()

class sale_order_line(Model):
    _inherit = 'sale.order.line'

    @only_for_referential('spree')
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
            erp_tax_id = False
            if resource.get('adjustments'):
                for adj in resource.get('adjustments', []):
                    erp_tax_id = account_tax.get_oeid(cr, uid, adj['originator_id'], 
                            external_session.referential_id.id, context=context)
            if erp_tax_id:
                line['tax_id'] = [(6, 0, [erp_tax_id])]
            else:
                line['tax_id'] = False
        return line

sale_order_line()