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
def _get_expected_oeid(self, cr, uid, external_id, referential_id, context=None):
    model_data_obj = self.pool.get('ir.model.data')
    model_data_ids = model_data_obj.search(cr, uid,
        [('name', '=', self.prefixed_id(external_id)),
         ('model', '=', self._name),
         ('referential_id', '=', referential_id)], context=context)
    model_data_id = model_data_ids and model_data_ids[0] or False
    expected_oe_id = False
    if model_data_id:
        expected_oe_id = model_data_obj.read(cr, uid, model_data_id, ['res_id'])['res_id']

        #Check if expected_oe_id really exists in model
        if expected_oe_id:
            domain = []
            if 'active' in self._columns.keys():
                domain = ['|', ('active', '=', False), ('active', '=', True)]
            domain.append(('id','=',expected_oe_id))
            oe_ids = self.search(cr, uid, domain)
            if not len(oe_ids):
                expected_oe_id = False

    return model_data_id, expected_oe_id

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
        
        total_pages = isinstance(resources, dict) and resources.get('pages', 1) or 1
    
        while page <= total_pages:
            resource_filter = self._get_filter(cr, uid, external_session, page, previous_filter=resource_filter, context=context)
            resources = self._get_external_resources(cr, uid, external_session, mapping=mapping, fields=None, params=resource_filter, context=context)
            if isinstance(resources,dict) and resources.get(external_resource_name, False):
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

@override(osv.osv, 'spree_')
@only_for_referential('spree')
def _transform_sub_mapping(self, cr, uid, external_session, convertion_type, resource, vals, sub_mapping_list,
                           mapping, mapping_id, mapping_line_filter_ids=None, defaults=None, context=None):
    """
    Used in _transform_one_external_resource in order to call the sub mapping

    @param sub_mapping_list: list of sub-mapping to apply
    @param resource: resource encapsulated in the object Resource or a dictionnary
    @param referential_id: external referential id from where we import the resource
    @param vals: dictionnary of value previously converted
    @param defauls: defaults value for the data imported
    @return: dictionary of converted data in OpenERP format
    """
    if not defaults:
        defaults={}
    ir_model_field_obj = self.pool.get('ir.model.fields')
    for sub_mapping in sub_mapping_list:
        sub_object_name = sub_mapping['child_mapping_id'][1]
        sub_mapping_id = sub_mapping['child_mapping_id'][0]
        if convertion_type == 'from_external_to_openerp':
            from_field = sub_mapping['external_field']
            if not from_field:
                from_field = "%s_%s" %(sub_object_name, sub_mapping_id)
            to_field = sub_mapping['internal_field']

        elif convertion_type == 'from_openerp_to_external':
            from_field = sub_mapping['internal_field']
            to_field = sub_mapping['external_field'] or 'hidden_field_to_split_%s'%from_field # if the field doesn't have any name we assume at that we will split it

        field_value = resource[from_field]
        sub_mapping_obj = self.pool.get(sub_object_name)
        sub_mapping_defaults = sub_mapping_obj._get_default_import_values(cr, uid, external_session, sub_mapping_id, defaults.get(to_field), context=context)

        if field_value:
            transform_args = [cr, uid, external_session, convertion_type, field_value]
            transform_kwargs = {
                'defaults': sub_mapping_defaults,
                'mapping': mapping,
                'mapping_id': sub_mapping_id,
                'mapping_line_filter_ids': mapping_line_filter_ids,
                'parent_data': vals,
                'context': context,
            }


            #Save submapping as external referential
            res_sub = sub_mapping_obj._record_external_resources(cr, uid, external_session, field_value,
                defaults=sub_mapping_defaults, mapping=mapping, mapping_id=sub_mapping_id, context=context)

            if sub_mapping['internal_type'] in ['one2many', 'many2many']:
                if not isinstance(field_value, list):
                    transform_args[4] = [field_value]
                if not to_field in vals:
                    vals[to_field] = []
                if convertion_type == 'from_external_to_openerp':
                    lines = sub_mapping_obj._transform_resources(*transform_args, **transform_kwargs)
                else:
                    mapping, sub_mapping_id = self._init_mapping(cr, uid, external_session.referential_id.id, \
                                                                    convertion_type=convertion_type,
                                                                    mapping=mapping,
                                                                    mapping_id=sub_mapping_id,
                                                                    context=context)
                    field_to_read = [x['internal_field'] for x in mapping[sub_mapping_id]['mapping_lines']]
                    sub_resources = sub_mapping_obj.read(cr, uid, field_value, field_to_read, context=context)
                    transform_args[4] = sub_resources
                    lines = sub_mapping_obj._transform_resources(*transform_args, **transform_kwargs)
                for line in lines:
                    if convertion_type == 'from_external_to_openerp':
                        if sub_mapping['internal_type'] == 'one2many':
                            #TODO refactor to search the id and alternative keys before the update
                            external_id = vals.get('external_id')
                            alternative_keys = mapping[mapping_id]['alternative_keys']
                            #search id of the parent
                            existing_ir_model_data_id, existing_rec_id = \
                                         self._get_oeid_from_extid_or_alternative_keys(
                                                                cr, uid, vals, external_id,
                                                                external_session.referential_id.id,
                                                                alternative_keys, context=context)
                            if not existing_rec_id:
                                existing_rec_id = self.get_oeid(cr, uid, external_id, external_session.referential_id.id)
                            vals_to_append = (0, 0, line)
                            #Search for existing submapping object and append instead of create record
                            sub_existing_rec_id = sub_mapping_obj.get_oeid(cr, uid, line.get('external_id'), external_session.referential_id.id)
                            if sub_existing_rec_id:
                                vals_to_append = (4, sub_existing_rec_id)

                            if existing_rec_id:
                                sub_external_id = line.get('external_id')
                                
                                if mapping[sub_mapping_id].get('alternative_keys'):
                                    sub_alternative_keys = list(mapping[sub_mapping_id]['alternative_keys'])
                                    if self._columns.get(to_field):
                                        related_field = self._columns[to_field]._fields_id
                                    elif self._inherit_fields.get(to_field):
                                        related_field = self._inherit_fields[to_field][2]._fields_id
                                    sub_alternative_keys.append(related_field)
                                    line[related_field] = existing_rec_id
                                    #search id of the sub_mapping related to the id of the parent
                                    sub_existing_ir_model_data_id, sub_existing_rec_id = \
                                                sub_mapping_obj._get_oeid_from_extid_or_alternative_keys(
                                                                    cr, uid, line, sub_external_id,
                                                                    external_session.referential_id.id,
                                                                    sub_alternative_keys, context=context)
                                    del line[related_field]

                                if 'external_id' in line:
                                    del line['external_id']
                                if sub_existing_rec_id:
                                    vals_to_append = (4, sub_existing_rec_id)     
                        vals[to_field].append(vals_to_append)
                    else:
                        vals[to_field].append(line)

            elif sub_mapping['internal_type'] == 'many2one':
                if convertion_type == 'from_external_to_openerp':
                    res = sub_mapping_obj._record_one_external_resource(cr, uid, external_session, field_value,
                            defaults=sub_mapping_defaults, mapping=mapping, mapping_id=sub_mapping_id, context=context)
                    vals[to_field] = res.get('write_id') or res.get('create_id')
                else:
                    sub_resource = sub_mapping_obj.read(cr, uid, field_value[0], context=context)
                    transform_args[4] = sub_resource
                    vals[to_field] = sub_mapping_obj._transform_one_resource(*transform_args, **transform_kwargs)
            else:
                raise except_osv(_('User Error'),
                                     _('Error with mapping : %s. Sub mapping can be only apply on one2many, many2one or many2many fields') % (sub_mapping['name'],))
    return vals