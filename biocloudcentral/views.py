"""Base views.
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

# ## Landing page with redirects

def home(request):
    launch_url = request.build_absolute_uri("/launch")
    if launch_url.startswith(("http://127.0.0.1", "http://localhost")):
        return redirect("/launch")
    else:
        return redirect("https://biocloudcentral.herokuapp.com/launch")

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
    print params
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


# ## CloudMan launch and configuration entry details
def launch(request):
    """Configure and launch CloudBioLinux and CloudMan servers.
    """
    if request.method == "POST":
        form = forms.CloudManForm(request.POST)
        if form.is_valid():
            print form.cleaned_data
            ec2_error = None
            try:
                # Create security group & key pair used when starting an instance
                ec2_conn = connect_ec2(form.cleaned_data['access_key'],
                                       form.cleaned_data['secret_key'],
                                       form.cleaned_data['cloud'])
                sg_name = create_cm_security_group(ec2_conn, form.cleaned_data['cloud'])
                kp_name, kp_material = create_key_pair(ec2_conn)
            except EC2ResponseError, err:
                ec2_error = err.error_message
            # associate form data with session for starting instance
            # and supplying download files
            if ec2_error is None:
                form.cleaned_data["kp_name"] = kp_name
                form.cleaned_data["kp_material"] = kp_material
                form.cleaned_data["sg_name"] = sg_name
                form.cleaned_data["cloud_type"] = form.cleaned_data['cloud'].cloud_type
                form.cleaned_data["cloud_name"] = form.cleaned_data['cloud'].name
                request.session["ec2data"] = form.cleaned_data
                if runinstance(request):
                    return redirect("/monitor")
                else:
                    form.non_field_errors = "A problem starting your instance. " \
                                            "Check the {0} cloud's console."\
                                            .format(form.cleaned_data['cloud'].name)
            else:
                form.non_field_errors = ec2_error
    else:
        # Select the first item in the clouds dropdown, thus potentially eliminating
        # that click for the most commonly used cloud. This does assume the most used
        # cloud is the first in the DB and that such an entry exists in the first place
        form = forms.CloudManForm(initial={'cloud': 1})
    return render(request, "launch.html", {"form": form}, context_instance=RequestContext(request))

def monitor(request):
    """Monitor a launch request and return offline files for console re-runs.
    """
    return render(request, "monitor.html", context_instance=RequestContext(request))

def runinstance(request):
    """Run a CloudBioLinux/CloudMan instance with current session credentials.
    """
    form = request.session["ec2data"]
    rs = None
    instance_type = form['instance_type']
    # Create EC2 connection with provided creds
    ec2_conn = connect_ec2(form["access_key"], form["secret_key"], form['cloud'])
    form["freenxpass"] = form["password"]
    if form['image_id']:
        image = models.Image.objects.get(pk=form['image_id'])
    else:
        try:
            image = models.Image.objects.get(cloud=form['cloud'], default=True)
        except models.Image.DoesNotExist:
            log.error("Cannot find an image to launch for cloud {0}".format(form['cloud']))
            return False
    rs = run_instance(ec2_conn=ec2_conn,
                      user_provided_data=form,
                      image_id=image.image_id,
                      kernel_id=image.kernel_id if image.kernel_id != '' else None,
                      ramdisk_id=image.ramdisk_id if image.ramdisk_id != '' else None,
                      key_name=form["kp_name"],
                      security_groups=[form["sg_name"]],
                      placement=form['placement'])
    if rs is not None:
        request.session['ec2data']['instance_id'] = rs.instances[0].id
        request.session['ec2data']['public_dns'] = rs.instances[0].public_dns_name
        request.session['ec2data']['image_id'] = rs.instances[0].image_id
        # Add an entry to the Usage table
        try:
            u = models.Usage(cloud_name=form["cloud_name"],
                             cloud_type=form["cloud_type"],
                             image_id=image.image_id,
                             instance_type=instance_type,
                             user_id=form["access_key"])
            u.save()
        except Exception, e:
            log.debug("Trouble saving Usage data: {0}".format(e))
        return True
    else:
        return False

def userdata(request):
    """Provide file download of user-data to re-start an instance.
    """
    ec2data = request.session["ec2data"]
    response = HttpResponse(mimetype='text/plain')
    response['Content-Disposition'] = 'attachment; filename={cluster_name}-userdata.txt'.format(
        **ec2data)
    ud = _compose_user_data(ec2data)
    response.write(ud)
    return response
    
def keypair(request):
    ec2data = request.session["ec2data"]
    response = HttpResponse(mimetype='text/plain')
    response['Content-Disposition'] = 'attachment; filename={kp_name}-key.pem'.format(
        **ec2data)
    response.write(ec2data['kp_material'])
    return response

def instancestate(request):
    form = request.session["ec2data"]
    ec2_conn = connect_ec2(form["access_key"], form["secret_key"], form['cloud'])
    state = instance_state(ec2_conn, form["instance_id"])
    return HttpResponse(simplejson.dumps(state), mimetype="application/json")

def dynamicfields(request):
    if request.is_ajax():
        if request.method == 'POST':
            cloud_id = request.POST.get('cloud_id', '')
            instance_types, image_ids = [], []
            if cloud_id != '':
                # Get instance types for the given cloud
                its = models.InstanceType.objects.filter(cloud=cloud_id)
                for it in its:
                    instance_types.append((it.tech_name, \
                        "{0} ({1})".format(it.pretty_name, it.description)))
                # Get Image IDs for the given cloud
                iids = models.Image.objects.filter(cloud=cloud_id)
                for iid in iids:
                    image_ids.append((iid.pk, \
                        "{0} ({1}){default}".format(iid.image_id, iid.description,
                        default="*" if iid.default is True else '')))
            state = {'instance_types': instance_types,
                     'image_ids': image_ids}
        else:
            log.error("Not a POST request")
    else:
        log.error("No XHR")
    return HttpResponse(simplejson.dumps(state), mimetype="application/json")

def get_placements(request):
    if request.is_ajax():
        if request.method == 'POST':
            cloud_id = request.POST.get('cloud_id', '')
            a_key = request.POST.get('a_key', '')
            s_key = request.POST.get('s_key', '')
            inst_type = request.POST.get('instance_type', '')
            placements = []
            if cloud_id != '' and a_key != '' and s_key != '' and inst_type != '':
                # Needed to get the cloud connection
                cloud = models.Cloud.objects.get(pk=cloud_id)
                ec2_conn = connect_ec2(a_key, s_key, cloud)
                placements = _find_placement(ec2_conn, inst_type, cloud.cloud_type, get_all=True)
                state = {'placements': placements}
        else:
            log.error("Not a POST request")
    else:
        log.error("No XHR")
    return HttpResponse(simplejson.dumps(state), mimetype="application/json")
