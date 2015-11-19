# -*- coding: utf-8 -*-
##############################################################################
#
# Author: Yannick Buron
# Copyright 2015, TODAY Clouder SASU
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License with Attribution
# clause as published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License with
# Attribution clause along with this program. If not, see
# <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, api, modules
import erppeek


class ClouderApplicationVersion(models.Model):
    """
    Add methods to manage the odoo specificities.
    """

    _inherit = 'clouder.application.version'

    @api.multi
    def build_application(self):
        """
        Build the archive with git or the anybox recipes.
        """
        super(ClouderApplicationVersion, self).build_application()
        if self.application_id.type_id.name == 'odoo':
            ssh = self.connect(self.archive_id.fullname)

            if self.application_id.buildfile.strip().startswith('git'):
                self.execute(ssh,
                             ['mkdir', '-p', self.full_archivepath + '/extra'])
                self.execute(ssh,
                             ['mkdir', '-p', self.full_archivepath + '/parts'])
                for command in self.application_id.buildfile.split('\n'):
                    if command.startswith('git'):
                        self.execute(ssh, [command],
                                     path=self.full_archivepath)
            elif self.application_id.buildfile.strip().startswith('[custom]'):
                for command in self.application_id.buildfile\
                        .replace('[custom]', '').split('\n'):
                    self.execute(ssh, [command],
                                 path=self.full_archivepath)
            else:
                self.execute(ssh, [
                    'echo "' + self.application_id.buildfile
                             .replace('"', '\\"').replace('$','\\$')
                             .replace('{','\\{').replace('}','\\}')
                    + '" >> ' +
                    self.full_archivepath + '/buildout.cfg'])
                self.execute(ssh, ['wget',
                                   'https://raw.github.com/buildout/buildout/'
                                   'master/bootstrap/bootstrap.py'],
                             path=self.full_archivepath)
                self.execute(ssh, ['virtualenv', 'sandbox'],
                             path=self.full_archivepath)
                self.execute(ssh,
                             ['yes | sandbox/bin/pip uninstall setuptools pip'],
                             path=self.full_archivepath)
                self.execute(ssh, ['sandbox/bin/python', 'bootstrap.py'],
                             path=self.full_archivepath)
                self.execute(ssh, ['bin/buildout'], path=self.full_archivepath)
                self.execute(ssh, [
                    'sed', '-i',
                    '"s/' + self.archive_path.replace('/', '\/') +
                    '/' + self.application_id.type_id.localpath
                    .replace('/', '\/') + '/g"',
                    self.full_archivepath + '/bin/start_odoo'
                ])
                self.execute(ssh, [
                    'sed', '-i',
                    '"s/' + self.archive_path.replace('/', '\/') +
                    '/' + self.application_id.type_id.localpath.
                    replace('/', '\/') + '/g"',
                    self.full_archivepath + '/bin/buildout'
                ])

            self.send(ssh,
                      modules.get_module_path('clouder_template_odoo') +
                      '/res/http.patch',
                      self.full_archivepath + '/parts/http.patch')
            self.execute(ssh, [
                'patch', self.full_archivepath + '/parts/odoo/openerp/http.py',
                '<', self.full_archivepath + '/parts/http.patch'])

            ssh.close()
        return


class ClouderContainer(models.Model):
    """
    Add methods to manage the postgres specificities.
    """

    _inherit = 'clouder.container'

    @property
    def base_backup_container(self):
        res = super(ClouderContainer, self).base_backup_container
        if self.application_id.type_id.name == 'odoo':
            res = self.childs['exec']
        return res

    @api.multi
    def deploy_post(self):
        super(ClouderContainer, self).deploy_post()
        if self.application_id.fullcode == 'odoo-data':
            config_file = '/opt/odoo/etc/odoo.conf'
            # addons_path = '/opt/odoo/' +\
            #               self.name + '/files/parts/odoo/addons,'
            # for extra_dir in sftp.listdir(
            #         '/opt/odoo/' + self.name + '/files/extra'):
            #     addons_path += '/opt/odoo/' + self.name +\
            #                    '/files/extra/' + extra_dir + ','
            # self.execute(ssh, ['sed', '-i', '"s/ADDONS_PATH/' +
            #                    addons_path.replace('/', '\/') + '/g"',
            #                    config_file])
            self.execute(['sed', '-i', '"s/APPLICATION/' +
                               self.application_id.parent_id.fullcode
                               .replace('-', '_') + '/g"', config_file])
            self.execute(['sed', '-i', 's/DB_SERVER/' +
                               self.db_server + '/g',
                               config_file])
            self.execute(['sed', '-i',
                               's/DB_USER/' + self.db_user + '/g',
                               config_file])
            self.execute(['sed', '-i', 's/DB_PASSWORD/' +
                               self.db_password + '/g',
                               config_file])


class ClouderService(models.Model):
    """
    Add methods to manage the odoo service specificities.
    """

    _inherit = 'clouder.service'

    @api.multi
    def deploy_post_service(self):
        """
        Update the odoo configuration file and supervisor conf.
        """
        super(ClouderService, self).deploy_post_service()
        if self.container_id.application_id.type_id.name == 'odoo':
            ssh = self.connect(
                self.container_id.fullname,
                username=self.container_id.application_id.type_id.system_user)

            config_file = '/opt/odoo/' + self.name + '/etc/config'
            self.execute(ssh,
                         ['mkdir', '-p', '/opt/odoo/' + self.name + '/etc'])
            self.send(ssh, modules.get_module_path('clouder_template_odoo') +
                      '/res/openerp.config', config_file)
            addons_path = '/opt/odoo/' +\
                          self.name + '/files/parts/odoo/addons,'
            sftp = ssh.open_sftp()
            for extra_dir in sftp.listdir(
                    '/opt/odoo/' + self.name + '/files/extra'):
                addons_path += '/opt/odoo/' + self.name +\
                               '/files/extra/' + extra_dir + ','
            sftp.close()
            self.execute(ssh, ['sed', '-i', '"s/ADDONS_PATH/' +
                               addons_path.replace('/', '\/') + '/g"',
                               config_file])
            self.execute(ssh, ['sed', '-i', '"s/APPLICATION/' +
                               self.container_id.application_id.code
                               .replace('-', '_') + '/g"', config_file])
            self.execute(ssh, ['sed', '-i', 's/SERVICE/' + self.name + '/g',
                               config_file])
            self.execute(ssh, ['sed', '-i', 's/DATABASE_SERVER/' +
                               self.database_server + '/g',
                               config_file])
            self.execute(ssh, ['sed', '-i',
                               's/DBUSER/' + self.db_user + '/g',
                               config_file])
            self.execute(ssh, ['sed', '-i', 's/DATABASE_PASSWORD/' +
                               self.database_password + '/g',
                               config_file])
            self.execute(ssh, ['sed', '-i', 's/PORT/' +
                               self.port['localport'] + '/g', config_file])
            self.execute(ssh, ['mkdir', '-p',
                               '/opt/odoo/' + self.name + '/filestore'])

            self.execute(ssh, ['echo "[program:' + self.name + ']" '
                               '>> /opt/odoo/supervisor.conf'])
            self.execute(ssh, [
                'echo "command=su odoo -c \'/opt/odoo/' + self.name +
                '/files/parts/odoo/odoo.py -c ' + config_file +
                '\'" >> /opt/odoo/supervisor.conf'])

            ssh.close()

        return

    @api.multi
    def purge_pre_service(self):
        """
        Purge supervisor conf.
        """
        super(ClouderService, self).purge_pre_service()
        if self.container_id.application_id.type_id.name == 'odoo':
            ssh = self.connect(
                self.container_id.fullname,
                username=self.container_id.application_id.type_id.system_user)
            self.execute(ssh, ['sed', '-i', '"/program:' + self.name + '/d"',
                               '/opt/odoo/supervisor.conf'])
            self.execute(ssh, [
                'sed', '-i',
                '"/command=su odoo -c \'\/opt\/odoo\/' + self.name + '/d"',
                '/opt/odoo/supervisor.conf'])
            ssh.close()

        return


class ClouderBase(models.Model):
    """
    Add methods to manage the odoo base specificities.
    """

    _inherit = 'clouder.base'

    @property
    def odoo_port(self):
        return self.container_id.childs['exec'] and self.container_id.childs['exec'].ports['odoo']['hostport']

    @api.multi
    def deploy_database(self):
        """
        Create the database with odoo functions.
        """
        if self.application_id.type_id.name == 'odoo':
            self.container_id.execute([
                'mkdir', '-p',
                '/opt/odoo/data/filestore/' +
                self.fullname_], username=self.application_id.type_id.system_user)

            if self.build == 'build':

                self.log("client = erppeek.Client('http://" +
                         self.container_id.server_id.ip + ":" +
                         self.odoo_port + "')")
                client = erppeek.Client(
                    'http://' + self.container_id.server_id.ip +
                    ':' + self.odoo_port)
                self.log(
                    "client.create_database('" +
                    self.container_id.childs['data'].db_password + "','" +
                    self.fullname_ + "'," + "demo=" + str(self.test) +
                    "," + "lang='" + self.lang + "'," +
                    "user_password='" + self.admin_password + "')")
                client.create_database(self.container_id.childs['data'].db_password,
                                       self.fullname_, demo=self.test,
                                       lang=self.lang,
                                       user_password=self.admin_password)

                return True
        return super(ClouderBase, self).deploy_database()

    @api.multi
    def deploy_build(self):
        """
        Update admin user, install account chart and modules.
        """
        res = super(ClouderBase, self).deploy_build()
        if self.application_id.type_id.name == 'odoo':
            self.log(
                "client = erppeek.Client('http://" +
                self.container_id.server_id.ip + ":" +
                self.odoo_port + "," +
                "db=" + self.fullname_ + "," +
                "user='admin', password=" + self.admin_password + ")")
            client = erppeek.Client(
                'http://' + self.container_id.server_id.ip + ':' +
                self.odoo_port,
                db=self.fullname_, user='admin',
                password=self.admin_password)

            self.log(
                "admin_id = client.model('ir.model.data')"
                ".get_object_reference('base', 'user_root')[1]")
            admin_id = client.model('ir.model.data')\
                .get_object_reference('base', 'user_root')[1]
            self.log("client.model('res.users').write([" + str(admin_id) +
                     "], {'login': " + self.admin_name + "})")
            client.model('res.users').write([admin_id],
                                            {'login': self.admin_name})

            self.log("extended_group_id = client.model('ir.model.data')"
                     ".get_object_reference('base', 'group_no_one')[1]")
            extended_group_id = client.model('ir.model.data')\
                .get_object_reference('base', 'group_no_one')[1]
            self.log("client.model('res.groups').write([" +
                     str(extended_group_id) + "], {'users': [(4, 1)]})")
            client.model('res.groups').write([extended_group_id],
                                             {'users': [(4, 1)]})

            if self.application_id.options['default_account_chart']['value']\
                    or self.options['account_chart']['value']:
                account_chart = self.options['account_chart']['value']\
                    or self.application_id.options[
                        'default_account_chart']['value']
                self.log("client.install('account_accountant', "
                         "'account_chart_install', '" + account_chart + "')")
                client.install('account_accountant', 'account_chart_install',
                               account_chart)
                self.log("client.execute('account.chart.template', "
                         "'install_chart', '" + account_chart + "', '" +
                         account_chart + "_pcg_chart_template', 1, 1)")
                client.execute('account.chart.template', 'install_chart',
                               account_chart,
                               account_chart + '_pcg_chart_template', 1, 1)

            if self.application_id.options['install_modules']['value']:
                modules = self.application_id.options['install_modules'][
                    'value'].split(',')
                for module in modules:
                    self.log("client.install(" + module + ")")
                    client.install(module)

        return res

    @api.multi
    def deploy_post(self):
        """
        Update odoo configuration.
        """
        res = super(ClouderBase, self).deploy_post()
        if self.application_id.type_id.name == 'odoo':
            self.log(
                "client = erppeek.Client('http://" +
                self.container_id.server_id.ip + ":" +
                self.odoo_port +
                ", db=" + self.fullname_ +
                ", user=" + self.admin_name +
                ", password=" + self.admin_password + ")")
            client = erppeek.Client(
                'http://' + self.container_id.server_id.ip + ':' +
                self.odoo_port,
                db=self.fullname_, user=self.admin_name,
                password=self.admin_password)

            self.log("company_id = client.model('ir.model.data')"
                     ".get_object_reference('base', 'main_company')[1]")
            company_id = client.model('ir.model.data')\
                .get_object_reference('base', 'main_company')[1]
            self.log("client.model('res.company').write([" + str(company_id) +
                     "], {'name':" + self.title + "})")
            client.model('res.company').write([company_id],
                                              {'name': self.title})

            self.log("config_ids = client.model('ir.config_parameter')"
                     ".search([('key','=','web.base.url')])")
            config_ids = client.model('ir.config_parameter').search(
                [('key', '=', 'web.base.url')])
            if config_ids:
                self.log("client.model('ir.config_parameter').write(" +
                         str(config_ids) + ", {'value': 'http://" +
                         self.fulldomain + "})")
                client.model('ir.config_parameter').write(config_ids, {
                    'value': 'http://' + self.fulldomain})
            else:
                self.log("client.model('ir.config_parameter')"
                         ".create({'key': 'web.base.url', 'value': 'http://" +
                         self.fulldomain + "})")
                client.model('ir.config_parameter').create(
                    {'key': 'web.base.url',
                     'value': 'http://' + self.fulldomain})

            self.log(
                "config_ids = client.model('ir.config_parameter')"
                ".search([('key','=','ir_attachment.location')])")
            config_ids = client.model('ir.config_parameter').search(
                [('key', '=', 'ir_attachment.location')])
            if config_ids:
                self.log("client.model('ir.config_parameter').write(" +
                         str(config_ids) + ", {'value': 'file:///filestore'})")
                client.model('ir.config_parameter').write(config_ids, {
                    'value': 'file:///filestore'})
            else:
                self.log("client.model('ir.config_parameter')"
                         ".create({'key': 'ir_attachment.location', "
                         "'value': 'file:///filestore'})")
                client.model('ir.config_parameter').create(
                    {'key': 'ir_attachment.location',
                     'value': 'file:///filestore'})
        return res

    @api.multi
    def deploy_create_poweruser(self):
        """
        Create poweruser.
        """
        res = super(ClouderBase, self).deploy_create_poweruser()
        if self.application_id.type_id.name == 'odoo':
            if self.poweruser_name and self.poweruser_email \
                    and self.admin_name != self.poweruser_name:
                self.log(
                    "client = erppeek.Client('http://" +
                    self.container_id.server_id.ip + ":" +
                    self.odoo_port + "," +
                    "db=" + self.fullname_ + "," + "user=" +
                    self.admin_name + ", password=" + self.admin_password + ")"
                )
                client = erppeek.Client(
                    'http://' + self.container_id.server_id.name +
                    ':' + self.odoo_port,
                    db=self.fullname_, user=self.admin_name,
                    password=self.admin_password)

                if self.test:
                    self.log(
                        "demo_id = client.model('ir.model.data')"
                        ".get_object_reference('base', 'user_demo')[1]")
                    demo_id = client.model('ir.model.data')\
                        .get_object_reference('base', 'user_demo')[1]
                    self.log("client.model('res.users').write([" +
                             str(demo_id) + "], {'login': 'demo_odoo', "
                                            "'password': 'demo_odoo'})")
                    client.model('res.users').write([demo_id],
                                                    {'login': 'demo_odoo',
                                                     'password': 'demo_odoo'})

                self.log("user_id = client.model('res.users')"
                         ".create({'login':'" + self.poweruser_email +
                         "', 'name':'" + self.poweruser_name + "', 'email':'" +
                         self.poweruser_email + "', 'password':'" +
                         self.poweruser_password + "'})")
                user = client.model('res.users').create(
                    {'login': self.poweruser_email,
                     'name': self.poweruser_name,
                     'email': self.poweruser_email,
                     'password': self.poweruser_password})

                if self.application_id.options['poweruser_group']['value']:
                    group = self.application_id.options['poweruser_group'][
                        'value'].split('.')
                    self.log("group_id = client.model('ir.model.data')"
                             ".get_object_reference('" + group[0] + "','" +
                             group[1] + "')[1]")
                    group_id = client.model('ir.model.data')\
                        .get_object_reference(group[0], group[1])[1]
                    self.log("client.model('res.groups').write([" +
                             str(group_id) + "], {'users': [(4, " +
                             str(user.id) + ")]})")
                    client.model('res.groups').write([group_id],
                                                     {'users': [(4, user.id)]})
        return res

    @api.multi
    def deploy_test(self):
        """
        Install test modules.
        """
        res = super(ClouderBase, self).deploy_test()
        if self.application_id.type_id.name == 'odoo':
            self.log(
                "client = erppeek.Client('http://" +
                self.container_id.server_id.ip + ":" +
                self.odoo_port + "," +
                "db=" + self.fullname_ + "," + "user=" +
                self.admin_name + ", password=" + self.admin_password + ")"
            )
            client = erppeek.Client(
                'http://' + self.container_id.server_id.ip + ':' +
                self.odoo_port,
                db=self.fullname_, user=self.admin_name,
                password=self.admin_password)

            if self.application_id.options['test_install_modules']['value']:
                modules = self.application_id.options[
                    'test_install_modules']['value'].split(',')
                for module in modules:
                    self.log("client.install(" + module + ")")
                    client.install(module)

        return res

    @api.multi
    def post_reset(self):
        """
        Disactive mail and cron on a duplicate base.
        """
        res = super(ClouderBase, self).post_reset()
        if self.application_id.type_id.name == 'odoo':
            self.log("client = erppeek.Client('http://" +
                     self.container_id.server_id.ip + ":" +
                     self.odoo_port +
                     ", db=" + self.fullname_ +
                     ", user=" + self.admin_name +
                     ", password=" + self.admin_password + ")")
            client = erppeek.Client(
                'http://' + self.container_id.server_id.name + ':' +
                self.odoo_port,
                db=self.fullname_, user=self.admin_name,
                password=self.admin_password)
            self.log("server_id = client.model('ir.model.data')"
                     ".get_object_reference('base', "
                     "'ir_mail_server_localhost0')[1]")
            server_id = client.model('ir.model.data')\
                .get_object_reference('base', 'ir_mail_server_localhost0')[1]
            self.log("client.model('ir.mail_server').write([" +
                     str(server_id) + "], {'smtp_host': 'mail.disabled.lol'})")
            client.model('ir.mail_server').write([server_id], {
                'smtp_host': 'mail.disabled.lol'})

            self.log("cron_ids = client.model('ir.cron')"
                     ".search(['|',('active','=',True),('active','=',False)])")
            cron_ids = client.model('ir.cron').search(
                ['|', ('active', '=', True), ('active', '=', False)])
            self.log("client.model('ir.cron').write(" +
                     str(cron_ids) + ", {'active': False})")
            client.model('ir.cron').write(cron_ids, {'active': False})

            self.container_id.execute([
                'cp', '-R', '/opt/odoo/' +
                self.env.context['service_parent_name'] + '/filestore/' +
                self.env.context['base_parent_fullname_'],
                '/opt/odoo/' + self.service_id.name + '/filestore/' +
                self.fullname_], username=self.application_id.type_id.system_user)

        return res

    @api.multi
    def update_base(self):
        """
        Update base module to update all others modules.
        """
        res = super(ClouderBase, self).update_base()
        if self.application_id.type_id.name == 'odoo':
            try:
                self.log("client = erppeek.Client('http://" +
                         self.container_id.server_id.ip + ":" +
                         self.odoo_port + "," +
                         "db=" + self.fullname_ + "," + "user=" +
                         self.admin_name + ", password=" +
                         self.admin_password + ")")
                client = erppeek.Client(
                    'http://' + self.container_id.server_id.name +
                    ':' + self.odoo_port,
                    db=self.fullname_, user=self.admin_name,
                    password=self.admin_password)
                self.log("client.upgrade('base')")
                client.upgrade('base')
            except:
                pass

        return res

    @api.multi
    def purge_post(self):
        """
        Remove filestore.
        """
        res = super(ClouderBase, self).purge_post()
        if self.application_id.type_id.name == 'odoo':
            self.container_id.execute([
                'rm', '-rf',
                '/opt/odoo/data/filestore/' + self.fullname_])
        return res


class ClouderBaseLink(models.Model):
    """
    Add methods to manage the odoo specificities.
    """

    _inherit = 'clouder.base.link'

    @api.multi
    def deploy_link(self):
        """
        Configure postfix to redirect incoming mail to odoo.
        """
        super(ClouderBaseLink, self).deploy_link()
        if self.name.name.code == 'postfix' \
                and self.base_id.application_id.type_id.name == 'odoo':
            try:
                self.log("client = erppeek.Client('http://" +
                         self.base_id.container_id.server_id.ip +
                         ":" +
                         self.base_id.odoo_port
                         + "," + "db=" + self.base_id.fullname_ + "," +
                         "user=" + self.base_id.admin_name + ", password=" +
                         self.base_id.admin_password + ")")
                client = erppeek.Client(
                    'http://' +
                    self.base_id.container_id.server_id.ip + ':' +
                    self.base_id.odoo_port,
                    db=self.base_id.fullname_,
                    user=self.base_id.admin_name, password=self.admin_password)
                self.log("server_id = client.model('ir.model.data')"
                         ".get_object_reference('base', "
                         "'ir_mail_server_localhost0')[1]")
                server_id = client.model('ir.model.data')\
                    .get_object_reference('base',
                                          'ir_mail_server_localhost0')[1]
                self.log("client.model('ir.mail_server').write([" +
                         str(server_id) +
                         "], {'name': 'postfix', 'smtp_host': 'postfix'})")
                client.model('ir.mail_server').write(
                    [server_id], {'name': 'postfix', 'smtp_host': 'postfix'})
            except:
                pass

            self.target.execute(['sed', '-i',
                               '"/^mydestination =/ s/$/, ' +
                               self.base_id.fulldomain + '/"',
                               '/etc/postfix/main.cf'])
            self.target.execute([
                'echo "@' + self.base_id.fulldomain + ' ' +
                self.base_id.fullname_ +
                '@localhost" >> /etc/postfix/virtual_aliases'])
            self.target.execute(['postmap', '/etc/postfix/virtual_aliases'])

            self.target.execute([
                "echo '" + self.base_id.fullname_ +
                ": \"|openerp_mailgate.py --host=" +
                self.base_id.container_id.server_id.name +
                " --port=" +
                self.base_id.odoo_port +
                " -u 1 -p " + self.base_id.admin_password + " -d " +
                self.base_id.fullname_ + "\"' >> /etc/aliases"])

            self.target.execute(['newaliases'])
            self.target.execute(['/etc/init.d/postfix', 'reload'])

    @api.multi
    def purge_link(self):
        """
        Purge postfix configuration.
        """
        super(ClouderBaseLink, self).purge_link()
        if self.name.name.code == 'postfix' \
                and self.base_id.application_id.type_id.name == 'odoo':
            self.target.execute([
                'sed', '-i',
                '"/^mydestination =/ s/, ' + self.base_id.fulldomain + '//"',
                '/etc/postfix/main.cf'])
            self.target.execute(['sed', '-i',
                               '"/@' + self.base_id.fulldomain + '/d"',
                               '/etc/postfix/virtual_aliases'])
            self.target.execute(['postmap', '/etc/postfix/virtual_aliases'])
            self.target.execute(['sed', '-i',
                               '"/d\s' + self.base_id.fullname_ + '/d"',
                               '/etc/aliases'])
            self.target.execute(['newaliases'])
            self.target.execute(['/etc/init.d/postfix', 'reload'])


class ClouderSave(models.Model):
    """
    Add methods to manage the odoo save specificities.
    """

    _inherit = 'clouder.save'

    @api.multi
    def deploy_base(self):
        """
        Backup filestore.
        """
        res = super(ClouderSave, self).deploy_base()
        if self.base_id.application_id.type_id.name == 'odoo':
            self.container_id.base_backup_container.execute([
                'cp', '-R',
                '/opt/odoo/data/filestore/' +
                self.base_id.fullname_,
                '/base-backup/' + self.name + '/filestore'], username=self.base_id.application_id.type_id.system_user)
        return res

    @api.multi
    def restore_base(self, base):
        """
        Restore filestore.
        """
        res = super(ClouderSave, self).restore_base(base)
        if self.base_id.application_id.type_id.name == 'odoo':
            base.container_id.base_backup_container.execute([
                'rm', '-rf',
                '/opt/odoo/data/filestore/' + self.base_id.fullname_], username=self.base_id.application_id.type_id.system_user)
            base.container_id.base_backup_container.execute([
                'cp', '-R',
                '/base-backup/restore-' + self.name + '/filestore',
                '/opt/odoo/data/filestore/' +
                self.base_id.fullname_], username=self.base_id.application_id.type_id.system_user)
        return res