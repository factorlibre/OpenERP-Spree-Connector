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
from base_external_referentials.external_osv import override, extend, ExternalSession
from tools.translate import _
from datetime import datetime
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT
import requests
import logging

_logger = logging.getLogger(__name__)

@extend(osv.osv)
def call_spree_method(self, cr, uid, external_session, method_url, method='GET', params=None, context=None):
    """
    :param string method_url: part of url that contains the method to call, for example products/3 to obtain the product with id 3
    :param string method: REST Method to be used 
    """
    if params is None:
        params = {}
    
    ext_ref = external_session.referential_id
    url = "%s/api/%s" % (ext_ref.location, method_url)
    headers = {'content-type': 'aplication/json', 'X-Spree-Token': ext_ref.apipass}

    res = requests.request(method, url, headers=headers, params=params)
    if res.status_code != requests.codes.ok:
        raise osv.except_osv(_('Error'), _('Spree HTTP Response error. URL: %s Code: %s' % (url, res.status_code)))
    if isinstance(res.json, list) or isinstance(res.json, dict):
        return res.json
    return res.json()


@override(osv.osv, 'spree_')
@only_for_referential('spree')
def _get_filter(self, cr, uid, external_session, page, previous_filter=None, context=None):
    """Abstract function that return the filter
    Can be overwriten in your module

    :param ExternalSession external_session : External_session that contain all params of connection
    :param int page: Page
    :param dict previous_filter: the previous filter
    :rtype: dict
    :return: dictionary with a filter
    """
    params = {}
    if page:
        params['page'] = page
    return params

@override(osv.osv, 'spree_')
@only_for_referential('spree')
def _get_external_resources(self, cr, uid, external_session, resource_filter=None, mapping=None, fields=None, params=None, context=None):
    search_vals = [('model', '=', self._name), ('referential_id', '=', external_session.referential_id.id)]
    mapping_ids = self.pool.get('external.mapping').search(cr, uid, search_vals)
    if params is None:
        params = {}
    if mapping is None:
        mapping = {mapping_ids[0] : self._get_mapping(cr, uid, external_session.referential_id.id, context=context)}
    ext_method = mapping[mapping_ids[0]]['external_get_method']
    ext_ref = external_session.referential_id
    headers = {'content-type': 'aplication/json', 'X-Spree-Token': ext_ref.apipass}

    url = ext_method
   
    resource = self.call_spree_method(cr, uid, external_session, url, method='GET', params=params, context=context)
    return resource

#No import method needed for spree. Read and search on the same call to the api
@override(osv.osv, 'spree_')
@only_for_referential('spree')
def _import_resources(self, cr, uid, external_session, defaults=None, context=None):
    """Abstract function to import resources form a specific object (like shop, referential...)

    :param ExternalSession external_session : External_session that contain all params of connection
    :param dict defaults: default value for the resource to create
    :rtype: dict
    :return: dictionary with the key "create_ids" and "write_ids" which containt the id created/written
    """
    external_session.logger.info("Start to import the ressource %s"%(self._name,))
    result = {"create_ids" : [], "write_ids" : []}
    mapping, mapping_id = self._init_mapping(cr, uid, external_session.referential_id.id, context=context)

    if mapping[mapping_id].get('mapping_lines', False):
        external_resource_name = mapping[mapping_id]['external_resource_name']
        resource_filter = None
        page = 1
        #paginated results in spree
        resource_filter = self._get_filter(cr, uid, external_session, page, previous_filter=resource_filter, context=context)
        resources = self._get_external_resources(cr, uid, external_session, mapping=mapping, params=resource_filter, fields=None, context=context)
        total_pages = resources.get('pages', 1)
    
        while page <= total_pages:
            resource_filter = self._get_filter(cr, uid, external_session, page, previous_filter=resource_filter, context=context)
            resources = self._get_external_resources(cr, uid, external_session, mapping=mapping, fields=None, params=resource_filter, context=context)
            if resources.get(external_resource_name, False):
                resources = resources[external_resource_name]
            if not isinstance(resources, list):
                resources = [resources]
            res = self._record_external_resources(cr, uid, external_session, resources, defaults=defaults, mapping=mapping, mapping_id=mapping_id, context=context)
            for key in result:
                result[key].append(res.get(key, []))
            page += 1
    return result

#No import method needed for spree. Read and search on the same call to the api
@override(osv.osv, 'spree_')
@only_for_referential('spree')
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