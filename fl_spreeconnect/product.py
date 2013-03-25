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
from base_external_referentials.decorator import only_for_referential, catch_error_in_report, open_report

class product_template(osv.osv):
    _inherit = 'product.template'

    @only_for_referential('spree')
    @open_report
    def _import_resources(self, *args, **kwargs):
        return super(product_template, self)._import_resources(*args, **kwargs)

product_template()

class product_product(osv.osv):
    _inherit = 'product.product'

    @only_for_referential('spree')
    def _get_filter(self, cr, uid, external_session, page, previous_filter=None, context=None):
        params = {}
        if page:
            params['page'] = page
        if external_session.referential_id and external_session.referential_id.last_product_import_date:
            params['q[updated_at_gt]'] = external_session.referential_id.last_product_import_date
        return params

    def update_spree_stock(self, cr, uid, ids, external_session, context=None):
        if context is None:
            context = {}
        template_pool = self.pool.get('product.template')
        for prod in self.browse(cr, uid, ids, context=context):
            ext_template_id = template_pool.get_extid(cr, uid,  prod.product_tmpl_id and prod.product_tmpl_id.id, external_session.referential_id.id, context=context)
            ext_product_id = self.get_extid(cr, uid, prod.id, external_session.referential_id.id, context=context)
            if not ext_template_id or not ext_product_id:
                continue
            update_product_url = "products/%s/variants/%s" % (ext_template_id, ext_product_id)
            params = {'variant[on_hand]': prod.qty_available}
            self.call_spree_method(cr, uid, external_session, update_product_url, method="PUT", params=params)
        return True
        
product_product()