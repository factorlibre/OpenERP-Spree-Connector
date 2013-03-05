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

from datetime import datetime

class external_referential(osv.osv):
    _inherit = 'external.referential'

    @only_for_referential('spree')
    def product_import(self, cr, uid, ids, context=None):
        self.import_resources(cr, uid, ids, 'product.template', context=context)
        self.write(cr, uid, ids, {'last_product_import_date': datetime.now()})
        return True

    @only_for_referential('spree')
    def image_import(self, cr, uid, ids, context=None):
        self.import_resources(cr, uid, ids, 'product.images', context=context)
        return True

external_referential()