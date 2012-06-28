"""APIs
"""
import logging
import copy

from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.template import RequestContext
from django.utils import simplejson
from django.shortcuts import render, redirect

from boto.exception import EC2ResponseError

from biocloudcentral import forms
from biocloudcentral import models
from biocloudcentral.amazon.launch import (connect_ec2, instance_state,
                                           create_cm_security_group,
                                           create_key_pair, run_instance,
                                           _compose_user_data, _find_placement)

log = logging.getLogger(__name__)

@csrf_exempt
def api_get_clouds(request):
    clouds = models.Cloud.objects.all()
    cloud_array = []
    for cloud in clouds:
        cloud_hash = {
                'id': cloud.id,
                'name': cloud.name,
                'cloud_type': cloud.cloud_type,
                'region_name': cloud.region_name,
                'bucket_default': cloud.bucket_default,
                'region_endpoint': cloud.region_endpoint,
                'ec2_port': cloud.ec2_port,
                'ec2_conn_path': cloud.ec2_conn_path,
                'cidr_range': cloud.cidr_range,
                'is_secure': cloud.is_secure,
                's3_host': cloud.s3_host,
                's3_port': cloud.s3_port,
                's3_conn_path': cloud.s3_conn_path,
                }
        cloud_array.append(cloud_hash)
    result = HttpResponse(simplejson.dumps(cloud_array))
    return result

@csrf_exempt
def api_get_instance_types(request):
    instance_types = models.InstanceType.objects.all()
    instance_type_array = []
    for instance_type in instance_types:
        instance_type_hash = {
                'id': instance_type.id,
                'cloud': str(instance_type.cloud),
                'pretty_name': instance_type.pretty_name,
                'tech_name': instance_type.tech_name,
                'description': instance_type.description,
                }
        instance_type_array.append(instance_type_hash)
    result = HttpResponse(simplejson.dumps(instance_type_array))
    return result

@csrf_exempt
def api_get_images(request):
    images = models.Image.objects.all()

    image_array = []
    for image in images:
        image_hash = {
                'id': image.id,
                'description': image.description,
                'cloud': str(image.cloud),
                'image_id': image.image_id,
                'default': image.default,
                'kernel_id': image.kernel_id,
                'ramdisk_id': image.ramdisk_id
                }
        image_array.append(image_hash)

    result_json = simplejson.dumps(image_array) 

    result = HttpResponse(result_json)
    return result

@csrf_exempt
def api_get_regions(request):
    cloud_name = request.GET.get('cloud_name', '')
    access_key = request.GET.get('access_key', '')
    secret_key = request.GET.get('secret_key', '')
    instance_type = request.GET.get('instance_type', '')
    regions = []
    if (cloud_name != '' and access_key != '' and secret_key != '' and instance_type != ''):
        cloud = models.Cloud.objects.get(name=cloud_name)
        ec2_conn = connect_ec2(access_key, secret_key, cloud)
        regions = _find_placement(ec2_conn, instance_type, cloud.cloud_type, get_all=True)
        result_text = simplejson.dumps(regions)
    else:
        result_text = "{'error': 'Please provide correct parameters'}" #STUB
    result = HttpResponse(result_text)
    return result

@csrf_exempt
def api_launch(request):
    params = copy.deepcopy(request.POST)

    ec2_error = None
    cloud = models.Cloud.objects.get(cloud_type=params['cloud'])
    params['cloud'] = cloud
    try:
        # Create security group & key pair used when starting an instance
        ec2_conn = connect_ec2(params['access_key'],
                               params['secret_key'],
                               cloud)
        sg_name = create_cm_security_group(ec2_conn, cloud)
        kp_name, kp_material = create_key_pair(ec2_conn)
    except EC2ResponseError, err:
        ec2_error = err.error_message

    if ec2_error is None:
        params["kp_name"] = kp_name
        params["kp_material"] = kp_material
        params["sg_name"] = sg_name
        params["cloud_type"] = cloud.cloud_type #"OpenStack" #cloud.cloud_type
        params["cloud_name"] = cloud.name #"NeCTAR" #cloud.name
        request.session["ec2data"] = params
        if params['image_id']:
            image = models.Image.objects.get(pk=params['image_id'])
        else:
            try:
                image = models.Image.objects.get(cloud=params['cloud'], default=True)
            except models.Image.DoesNotExist:
                log.error("Cannot find an image to launch for cloud {0}".format(params['cloud']))
                result = HttpResponse(simplejson.dumps("ERROR"))
                return result

        ec2_conn = connect_ec2(params["access_key"], params["secret_key"], cloud)
        rs = run_instance(ec2_conn=ec2_conn,
                      user_provided_data=params,
                      image_id=image.image_id,
                      kernel_id=image.kernel_id if image.kernel_id != '' else None,
                      ramdisk_id=image.ramdisk_id if image.ramdisk_id != '' else None,
                      key_name=params["kp_name"],
                      security_groups=[params["sg_name"]])#,
                      #placement=params['placement'])
        ## TODO: Save usage file?
        result_text = str(rs)


    else:
        result_text = ec2_error

    result = HttpResponse(simplejson.dumps(result_text))
    return result

