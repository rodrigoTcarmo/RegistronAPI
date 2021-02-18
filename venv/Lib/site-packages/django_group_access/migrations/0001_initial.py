# encoding: utf-8
import datetime
from south.db import db
from south.v2 import SchemaMigration
from django.db import models

class Migration(SchemaMigration):

    def forwards(self, orm):
        
        # Adding model 'AccessGroup'
        db.create_table('django_group_access_accessgroup', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=64)),
            ('supergroup', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('can_be_shared_with', self.gf('django.db.models.fields.BooleanField')(default=True)),
        ))
        db.send_create_signal('django_group_access', ['AccessGroup'])

        # Adding M2M table for field members on 'AccessGroup'
        db.create_table('django_group_access_accessgroup_members', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('accessgroup', models.ForeignKey(orm['django_group_access.accessgroup'], null=False)),
            ('user', models.ForeignKey(orm['auth.user'], null=False))
        ))
        db.create_unique('django_group_access_accessgroup_members', ['accessgroup_id', 'user_id'])

        # Adding M2M table for field can_share_with on 'AccessGroup'
        db.create_table('django_group_access_accessgroup_can_share_with', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('from_accessgroup', models.ForeignKey(orm['django_group_access.accessgroup'], null=False)),
            ('to_accessgroup', models.ForeignKey(orm['django_group_access.accessgroup'], null=False))
        ))
        db.create_unique('django_group_access_accessgroup_can_share_with', ['from_accessgroup_id', 'to_accessgroup_id'])

        # Adding M2M table for field auto_share_groups on 'AccessGroup'
        db.create_table('django_group_access_accessgroup_auto_share_groups', (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('from_accessgroup', models.ForeignKey(orm['django_group_access.accessgroup'], null=False)),
            ('to_accessgroup', models.ForeignKey(orm['django_group_access.accessgroup'], null=False))
        ))
        db.create_unique('django_group_access_accessgroup_auto_share_groups', ['from_accessgroup_id', 'to_accessgroup_id'])


    def backwards(self, orm):
        
        # Deleting model 'AccessGroup'
        db.delete_table('django_group_access_accessgroup')

        # Removing M2M table for field members on 'AccessGroup'
        db.delete_table('django_group_access_accessgroup_members')

        # Removing M2M table for field can_share_with on 'AccessGroup'
        db.delete_table('django_group_access_accessgroup_can_share_with')

        # Removing M2M table for field auto_share_groups on 'AccessGroup'
        db.delete_table('django_group_access_accessgroup_auto_share_groups')


    models = {
        'auth.group': {
            'Meta': {'object_name': 'Group'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '80'}),
            'permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'})
        },
        'auth.permission': {
            'Meta': {'ordering': "('content_type__app_label', 'content_type__model', 'codename')", 'unique_together': "(('content_type', 'codename'),)", 'object_name': 'Permission'},
            'codename': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'content_type': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['contenttypes.ContentType']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '50'})
        },
        'auth.user': {
            'Meta': {'object_name': 'User'},
            'date_joined': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'email': ('django.db.models.fields.EmailField', [], {'max_length': '75', 'blank': 'True'}),
            'first_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'groups': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Group']", 'symmetrical': 'False', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'is_active': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'is_staff': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'is_superuser': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'last_login': ('django.db.models.fields.DateTimeField', [], {'default': 'datetime.datetime.now'}),
            'last_name': ('django.db.models.fields.CharField', [], {'max_length': '30', 'blank': 'True'}),
            'password': ('django.db.models.fields.CharField', [], {'max_length': '128'}),
            'user_permissions': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.Permission']", 'symmetrical': 'False', 'blank': 'True'}),
            'username': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '30'})
        },
        'contenttypes.contenttype': {
            'Meta': {'ordering': "('name',)", 'unique_together': "(('app_label', 'model'),)", 'object_name': 'ContentType', 'db_table': "'django_content_type'"},
            'app_label': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'model': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'})
        },
        'django_group_access.accessgroup': {
            'Meta': {'ordering': "('name',)", 'object_name': 'AccessGroup'},
            'auto_share_groups': ('django.db.models.fields.related.ManyToManyField', [], {'related_name': "'auto_share_groups_rel_+'", 'blank': 'True', 'to': "orm['django_group_access.AccessGroup']"}),
            'can_be_shared_with': ('django.db.models.fields.BooleanField', [], {'default': 'True'}),
            'can_share_with': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['django_group_access.AccessGroup']", 'symmetrical': 'False', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'members': ('django.db.models.fields.related.ManyToManyField', [], {'to': "orm['auth.User']", 'symmetrical': 'False', 'blank': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '64'}),
            'supergroup': ('django.db.models.fields.BooleanField', [], {'default': 'False'})
        }
    }

    complete_apps = ['django_group_access']
