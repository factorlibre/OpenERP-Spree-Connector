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
from base_external_referentials.decorator import only_for_referential, commit_now
from base_external_referentials.external_osv import override, extend
from tools.translate import _
from datetime import datetime
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
import requests
import logging

_logger = logging.getLogger(__name__)

@extend(osv.osv)
def call_spree_method(self, cr, uid, external_session, method_url, method='get', context=None):
    """
    :param string method_url: part of url that contains the method to call, for example products/3 to obtain the product with id 3
    :param string method: REST Method to be used 
    """
    if not hasattr(requests, method):
        _logger.warning("Requests has no method %s" % (method))
    ext_ref = external_session.referential_id
    url = "%s/api/%s" % (ext_ref.location, ext_ref.method_url)
    headers = {'content-type': 'aplication/json', 'X-Spree-Token': ext_ref.apipass}

    res = getattr(requests, method)(url, headers)
    if res.status_code != requests.codes.ok:
        raise osv.except_osv(_('Error'), _('Spree HTTP Response error. URL: %s Code: %s' % (url, res.status_code)))
    if isinstance(res.json, list) or isinstance(res.json, dict):
        return res.json
    return res.json()



@override(osv.osv, 'spree_')
@only_for_referential('spree')
def _get_external_resources(self, cr, uid, external_session, external_id, resource_filter=None, mapping=None, fields=None, context=None):
    search_vals = [('model', '=', self._name), ('referential_id', '=', external_session.referential_id.id)]
    mapping_ids = self.pool.get('external.mapping').search(cr, uid, search_vals)
    if mapping is None:
        mapping = {mapping_ids[0] : self._get_mapping(cr, uid, external_session.referential_id.id, context=context)}
    ext_method = mapping[mapping_ids[0]]['external_get_method']
    ext_ref = external_session.referential_id
    headers = {'content-type': 'aplication/json', 'X-Spree-Token': ext_ref.apipass}

    url = "%s/%s" % (ext_method, external_id)

    resource = self.call_spree_method(cr, uid, external_session, url, method='get', context=context)
    return resource


