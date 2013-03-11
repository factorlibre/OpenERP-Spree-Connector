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
import logging

from datetime import datetime

_logger = logging.getLogger(__name__)

class sale_shop(osv.osv):
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
            products = self.call_spree_method(cr, uid, external_session, 'products')
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
                products = self.call_spree_method(cr, uid, external_session, 'products', params={'page': page})
            return True

sale_shop()