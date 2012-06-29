from django.conf.urls.defaults import patterns, include, url

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    # Examples:
    url(r'^$', 'biocloudcentral.views.home', name='home'),
    url(r'^launch$', 'biocloudcentral.views.launch', name='launch'),
    url(r'^monitor$', 'biocloudcentral.views.monitor', name='monitor'),
    url(r'^ud$', 'biocloudcentral.views.userdata', name='ud'),
    url(r'^kp$', 'biocloudcentral.views.keypair', name='kp'),
    url(r'^state$', 'biocloudcentral.views.instancestate', name='inst_state'),
    url(r'^dynamic-fields$', 'biocloudcentral.views.dynamicfields', name='dynamic_fields'),
    url(r'^get-placements$', 'biocloudcentral.views.get_placements', name='get_placements'),
    # url(r'^biocloudcentral/', include('biocloudcentral.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),

    # API
    url(r'^api/launch$', 'biocloudcentral.api.api_launch', name='api_launch'),
    url(r'^api/get_images$', 'biocloudcentral.api.api_get_images', name='api_get_images'),
    url(r'^api/get_clouds$', 'biocloudcentral.api.api_get_clouds', name='api_get_clouds'),
    url(r'^api/get_instance_types$', 'biocloudcentral.api.api_get_instance_types', name='api_get_instance_types'),
    url(r'^api/get_regions$', 'biocloudcentral.api.api_get_regions', name='api_get_regions'),
    url(r'^api/state$', 'biocloudcentral.api.api_instancestate', name='api_instancestate'),

)
