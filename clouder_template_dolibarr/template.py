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


class ClouderContainer(models.Model):
    """
    Add methods to manage the dolibarr specificities.
    """

    _inherit = 'clouder.container'

    @api.multi
    def deploy_post(self):
        super(ClouderContainer, self).deploy_post()

        if self.application_id.type_id.name == 'dolibarr':
            self.execute(
                         ['wget', '-q', 'http://www.dolibarr.org/files/dolibarr.tgz',
                          'dolibarr.tgz'], path='/var/www/', username='www-data')
            self.execute(['tar', '-xzf', 'dolibarr.tgz'],
                         path='/var/www', username='www-data')
            self.execute(['rm', '-rf', './*.tgz'],
                         path='/var/www', username='www-data')
            self.execute(['mv', 'dolibarr-*/', 'dolibarr/'],
                         path='/var/www', username='www-data')
            self.execute(['touch', 'htdocs/conf/conf.php'],
                         path='/var/www/dolibarr', username='www-data')
            self.execute(['mkdir', 'documents'],
                         path='/var/www/dolibarr', username='www-data')


class ClouderBase(models.Model):
    """
    Add methods to manage the shinken specificities.
    """

    _inherit = 'clouder.base'

    @api.multi
    def deploy_build(self):
        """
        Configure nginx.
        """
        res = super(ClouderBase, self).deploy_build()
        if self.application_id.type_id.name == 'dolibarr':

            config_file = '/etc/nginx/sites-available/' + self.fullname
            self.container_id.send(
                      modules.get_module_path('clouder_template_dolibarr') +
                      '/res/nginx.config', config_file)
            self.container_id.execute(['sed', '-i', '"s/BASE/' + self.name + '/g"',
                               config_file])
            self.container_id.execute(['sed', '-i',
                               '"s/DOMAIN/' + self.domain_id.name + '/g"',
                               config_file])
            self.container_id.execute(['ln', '-s',
                               '/etc/nginx/sites-available/' + self.fullname,
                               '/etc/nginx/sites-enabled/' + self.fullname])
            self.container_id.execute(['/etc/init.d/nginx', 'reload'])

        return res

    @api.multi
    def purge_post(self):
        """
        Purge from nginx configuration.
        """
        super(ClouderBase, self).purge_post()
        if self.application_id.type_id.name == 'dolibarr':
            self.container_id.execute(['rm', '-rf',
                               '/etc/nginx/sites-enabled/' + self.fullname])
            self.container_id.execute([
                'rm', '-rf', '/etc/nginx/sites-available/' + self.fullname])
            self.container_id.execute(['/etc/init.d/nginx', 'reload'])
