import ldap

from keystone.backends.api import BaseTenantAPI
from keystone.backends.sqlalchemy.api.tenant import TenantAPI as SQLTenantAPI

from .. import models
from .base import  BaseLdapAPI, add_redirects


class TenantAPI(BaseLdapAPI, BaseTenantAPI):
    DEFAULT_TREE_DN = 'ou=Groups,dc=example,dc=com'
    DEFAULT_STRUCTURAL_CLASSES = ['groupOfNames']
    options_name = 'tenant'
    object_class = 'keystoneTenant'
    model = models.Tenant
    attribute_mapping = {'desc': 'description', 'enabled': 'keystoneEnabled',
                         'name': 'keystoneName'}

    def get_by_name(self, name, filter=None):
         tenants = self.get_all('(keystoneName=%s)' % \
                             (ldap.filter.escape_filter_chars(name),))
         try:
             return tenants[0]
         except IndexError:
             return None

    def create(self, values):
        id_list = [0]

        conn = self.api.get_connection()
        query = '(objectClass=keystoneTenant)'
        list = conn.search_s(self.tree_dn, ldap.SCOPE_ONELEVEL, query)
        for dn, attrs in list:
            id_list.append(int(self.api.tenant._dn_to_id(dn)))

        id_list.sort()
        id_max = id_list[-1]

        values['id'] = str(id_max + 1)

        return super(TenantAPI, self).create(values)

    def get_user_tenants(self, user_id, include_roles=True):
        user_dn = self.api.user._id_to_dn(user_id)
        query = '(member=%s)' % (user_dn,)
        memberships = self.get_all(query)
        if include_roles:
            roles = self.api.role.ref_get_all_tenant_roles(user_id)
            for role in roles:
                memberships.append(self.get(role.tenant_id))
        return memberships

    def tenants_for_user_get_page(self, user, marker, limit):
        return self._get_page(marker, limit, self.get_user_tenants(user.id))

    def tenants_for_user_get_page_markers(self, user, marker, limit):
        return self._get_page_markers(marker, limit,
                        self.get_user_tenants(user.id))

    def is_empty(self, id):
        tenant = self._ldap_get(id)
        members = tenant[1].get('member', [])
        if self.use_dumb_member:
            empty = members == [self.DUMB_MEMBER_DN]
        else:
            empty = len(members) == 0
        return empty and len(self.api.role.get_role_assignments(id)) == 0

    def get_role_assignments(self, tenant_id):
        return self.api.role.get_role_assignments(tenant_id)

    def add_user(self, tenant_id, user_id):
        conn = self.api.get_connection()
        conn.modify_s(self._id_to_dn(tenant_id),
            [(ldap.MOD_ADD, 'member', self.api.user._id_to_dn(user_id))])

    def remove_user(self, tenant_id, user_id):
        conn = self.api.get_connection()
        conn.modify_s(self._id_to_dn(tenant_id),
            [(ldap.MOD_DELETE, 'member', self.api.user._id_to_dn(user_id))])

    def get_users(self, tenant_id):
        tenant = self._ldap_get(tenant_id)
        res = []
        for user_dn in tenant[1].get('member', []):
            if self.use_dumb_member and user_dn == self.DUMB_MEMBER_DN:
                continue
            res.append(self.api.user.get(self.api.user._dn_to_id(user_dn)))
        return res

    add_redirects(locals(), SQLTenantAPI, ['get_all_endpoints'])
