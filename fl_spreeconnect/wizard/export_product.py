# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) Factor Libre.
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

from openerp.osv.orm import TransientModel
from openerp.osv import fields
from openerp.osv.osv import except_osv
from openerp.tools.translate import _
from base_external_referentials.external_osv import ExternalSession

class export_campaign_wizard(TransientModel):
    _name = 'export.campaign.wizard'

    _columns = {
        'shop': fields.many2many('sale.shop', 'shop_campaign_rel', 'shop_id', 'product_id', 'Shop', required=True),
    }

    def export(self, cr, uid, id, context=None):
        if context is None:
            context={}
        shop_ids = self.read(cr, uid, id, context=context)[0]['shop']
        sale_shop_obj = self.pool.get('sale.shop')
        product_ids = context['active_ids']
        product_pool = self.pool.get('product.product')

        for shop in sale_shop_obj.browse(cr, uid, shop_ids, context=context):
            if not shop.referential_id:
                raise except_osv(_("User Error"),
                                _("The shop '%s' doesn't have any external "
                                "referential are you sure that it's an external sale shop?"
                                )%(shop.name,))
            external_session = ExternalSession(shop.referential_id, shop)
            context = sale_shop_obj.init_context_before_exporting_resource(cr, uid, external_session, shop.id, 'account.analytic.account', context=context)
            for campaign_id in campaign_ids:
                campaign_obj._export_one_resource(cr, uid, external_session, campaign_id, context=context)
        return {'type': 'ir.actions.act_window_close'}