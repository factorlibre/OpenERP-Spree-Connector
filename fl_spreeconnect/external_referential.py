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
            id = id[0]
        referential = self.browse(cr, uid, id, context=context)
        headers = {'content-type': 'application/json', 'X-Spree-Token': referential.apipass}
        #Test connection returning headers
        connection = requests.head("%s/api/products.json" % referential.location, headers=headers)
        if connection.status_code != requests.codes.ok:
            if config['debug_mode']: raise
            raise osv.except_osv(_("Connection Error"), _("Could not connect to the Spree webservice\nCheck the webservice URL and password\nHTTP error code: %s"%connection.status_code))
        return True

    @only_for_referential('spree')
    def product_import(self, cr, uid, ids, context=None):
        self.import_resources(cr, uid, ids, 'product.product', context=context)
        self.write(cr, uid, ids, {'last_product_import_date': datetime.now()})
        return True

external_referential()