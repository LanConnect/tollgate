"""tollgate frontend views
Copyright 2008-2012 Michael Farrell

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from django import forms
import tollgate
from django.shortcuts import render, get_object_or_404, redirect
from tollgate.frontend.models import *
from django.http import HttpResponseRedirect, HttpResponseForbidden, HttpResponse
from datetime import datetime, timedelta
from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate
from django.contrib.auth import login as login_do
from django.contrib.auth import logout as logout_do
from django.template import RequestContext as RequestContextOriginal
from django.db import transaction
from traceback import extract_tb
import sys
from django.utils.translation import ugettext as _
from tollgate.frontend.forms import *
from django.core.exceptions import *
from django.contrib import messages
import random

# ...

class NoCurrentEventException(Exception): pass


class RequestContext(RequestContextOriginal):
	"Our version of the RequestContext that includes additional stuff."
	settings = settings
	themes = THEME_CHOICES
	tollgate_version = tollgate.__version__

def controller_error(request):
	return render(request, 'frontend/controller-error.html', {'excinfo': "%s: %s" % (sys.exc_type, sys.exc_value), 'traceback': extract_tb(sys.exc_traceback)})

def login(request):
	if request.user.is_authenticated():
		# already logged in
		return HttpResponseRedirect('/')

	if request.method == 'POST':
		f = LoginForm(request.POST)
		if not f.is_valid():
			return render(request, 'frontend/login.html', {'f': f, 'fail': False})

		# check if the user has a password set already
		user = authenticate(username=f.cleaned_data['username'], password=f.cleaned_data['password'])
		if user == None:
			d = {
				'f': f, 'fail': True, 'fail_credentials': True,
			}

			return render(request, 'frontend/login.html', d)
		else:
			# user already exists locally, lets use that stuff instead.
			if not user.is_active:
				d = {
					'f': f, 'fail': True, 'fail_disabled': True,
				}

				return render(request, 'frontend/login.html', d)

			# success!
			login_do(request, user)

			# also try to sync firewall in this operation
			# reason being is the next operation could change the amount of quota a user has.
			profile = get_userprofile(user)
			try:
				sync_user_connections(profile)
			except:
				# why did this error out?  it probably doesn't need to.
				#return controller_error(request)
				pass

			current_event = get_current_event()
			# check if they need to have their attendance reset
			if not has_userprofile_attended(current_event, profile):
				if user.has_perm('frontend.can_register_attendance'):
					# user is allowed to sign other people in, so let them login.

					# note to them that they need attendance set.
					messages.warning(request, 'Your account does not have attendance registered.  Login was allowed so that you can do this.')

					# return them to homepage
					return HttpResponseRedirect('/')

				else:
					# failure
					d = {
						'f': f, 'fail': True,
						'fail_attendance': True,
					}

					# log them out if they've already had a useraccount for some reason
					logout_do(request)

					return render(request, 'frontend/login.html', d)

			attendance = get_attendance_currentevent(profile)

			# turn on the user's internet connection if they say they wanted it on
			if f.cleaned_data['internet'] or profile.internet_on:
				try:
					enable_user_quota(attendance)
				except:
					return controller_error(request)

			if f.cleaned_data['internet']:
				# we need to do an internet login as well for the user.
				# lets send them across
				return HttpResponseRedirect('/internet/login/here/')

			# no internet login requested
			# send to homepage
			return HttpResponseRedirect('/')
	else:
		f = LoginForm()
		return render(request, 'frontend/login.html', {'f': f, 'fail': False})

def logout(request):
	logout_do(request)
	return render(request, 'frontend/logout.html')

@login_required
def internet_login_here(request):
	# find my MAC address
	ip = request.META['REMOTE_ADDR']
	mac = get_mac_address(ip)
	if mac == None:
		# failure
		return render(request, 'frontend/internet_login_here-failure.html')
	if settings.ONLY_CONSOLE and not is_console(mac):
		return render(request, 'frontend/not-a-console.html')

	#mac = mac.replace(":", "")

	return HttpResponseRedirect('/internet/login/' + mac + '/')

@login_required
def internet_login(request, mac_address):
	# we assume urls were setup right so we don't have to fux around with validation.

	# TODO: check that ip address is in our subnet

	refresh_networkhost_quick()

	user = request.user
	profile = get_userprofile(user)

	if request.method == 'POST':
		# we got a POST request.  this is someone accepting the TOS
		profile.accepted_tos = True
		profile.save()

		# continue through...

	# tos is now done externally.
	#if not profile.accepted_tos:
	#	return render(request, 'frontend/tos.html', {'u': user})

	# find the user's attendance
	current_event = get_current_event()
	if current_event is None and not user.is_staff:
		return render(request, 'frontend/event-not-active.html')

	if not has_userprofile_attended(current_event, profile):
		return render(request, 'frontend/not-signed-in.html', {'event': current_event})
	attendance = get_userprofile_attendance(current_event, profile)

	# register the computer's ownership permanently
	try:
		h = NetworkHost.objects.get(mac_address__iexact=mac_address)
		# check that the client is a console
		if (not settings.ONLY_CONSOLE) or h.is_console:
			ip = get_ip_address(mac_address)
		else:
			return render(request, 'frontend/not-a-console.html')


		# check that the IP is infact in the subnet
		if not in_lan_subnet(h.ip_address):
			# not in subnet, throw error
			return render(request, 'frontend/internet_login-not_in_subnet.html', {'mac': mac_address.upper()})

		# always update the IP address, even if it's there already.
		if ip != None:
			h.ip_address = ip

		old_owner = h.user_profile
		if h.user_profile != None and h.user_profile != profile:
			# only allow this if it is the current machine
			ip = request.META['REMOTE_ADDR']
			mac = get_mac_address(ip)
			if mac.upper() == mac_address.upper():
				# mac addresses match, allow the change
				h.user_profile = profile
			else:
				# this isn't the current machine, disallow the change
				return render(request, 'frontend/internet_login-already_owned.html', {'mac': mac_address.upper()})
		else:
			h.user_profile = profile

		# before we save, we must log this change if there is in fact a change
		if old_owner != h.user_profile:
			NetworkHostOwnerChangeEvent.objects.create(old_owner=old_owner, new_owner=h.user_profile, network_host=h)

		h.save()

	except ObjectDoesNotExist:
		# can't get mac address from database, another glitch in the matrix
		return render(request, 'frontend/arp-cache-error.html')

	try:
		# sync the database to the firewall
		sync_user_connections(profile)

		# enable internet access
		enable_user_quota(attendance)
	except:
		# connection failure
		return controller_error(request)
	# show the pretty page
	return render(request, 'frontend/internet_login.html', {'mac': mac_address, 'u': user})

@login_required
def internet_disown(request, host_id):
	h = get_object_or_404(NetworkHost, id=host_id)
	profile = get_userprofile(request.user)

	if h.user_profile == profile or request.user.has_perm('frontend.can_view_ownership'):
		# it's owned by me or i'm allowed to change it, so i can disown it.
		# make sure "profile" variable is set correctly in this context, for handling third party disownership.
		profile = h.user_profile
		NetworkHostOwnerChangeEvent.objects.create(old_owner=profile, new_owner=None, network_host=h)
		h.user_profile = None
		h.save()

		# resync internet for user
		sync_user_connections(profile)
		if request.META.has_key('HTTP_REFERER'):
			return HttpResponseRedirect(request.META['HTTP_REFERER'])
		else:
			return HttpResponseRedirect('/internet/')
	else:
		# not allowed.
		return HttpResponseForbidden()

@login_required
def host_refresh_quick(request):
	refresh_networkhost_quick()
	return HttpResponseRedirect('/internet/')


@login_required
def internet(request):
	refresh_networkhost_quick()
	hosts = get_unclaimed_online_hosts()
	return render(request, 'frontend/internet.html', {'hosts': hosts, 'offline': False})

@login_required
def internet_offline(request):
	refresh_networkhost_quick()
	hosts = get_unclaimed_offline_hosts()
	return render(request, 'frontend/internet.html', {'hosts': hosts, 'offline': True})

@login_required
def quota(request):
	# get the amount of quota the user has
	user = request.user
	profile = get_userprofile(user)
	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html')
	try:
		attendance = get_userprofile_attendance(current_event, profile)
	except ObjectDoesNotExist:
		return render(request, 'frontend/not-signed-in.html', {'event': current_event})

	quota_update_fail = False
	try:
		# make sure there hasn't been an update in the last 2 minutes.  if there has, don't bother grabbing quota data.
		if not NetworkUsageDataPoint.objects.filter(event_attendance=attendance, when__gte=datetime.now()-timedelta(minutes=2)):
			refresh_quota_usage(attendance)
	except:
		quota_update_fail = True

	my_hosts = NetworkHost.objects.filter(user_profile__exact=profile)

	has_free_reset = False
	could_get_a_reset_later = False
	if attendance.quota_multiplier == 1:
		# don't offer a reset unless they've used 70% of their quota already.
		has_free_reset = attendance.usage_fraction() > 0.7
		could_get_a_reset_later = not has_free_reset
	return render(request, 'frontend/quota.html', {'my_hosts': my_hosts, 'attendance': attendance, 'quota_update_fail': quota_update_fail, 'profile': profile, 'has_free_reset' : has_free_reset, 'could_get_a_reset_later': could_get_a_reset_later})

@login_required
def quota_on(request):
	user = request.user
	profile = get_userprofile(user)
	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html')
	attendance = get_userprofile_attendance(current_event, profile)

	try:
		enable_user_quota(attendance)
		sync_user_connections(profile)
	except:
		return controller_error(request)

	return HttpResponseRedirect('/quota/')

@login_required
def quota_user_reset(request):
	user = request.user
	profile = get_userprofile(user)
	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html')
	attendance = get_userprofile_attendance(current_event, profile)

	#TODO: Make it check you have used at least 70% of your quota before continuing.

	if request.method == "POST":
		reset_form = ResetLectureForm(request.POST)

		if reset_form.check_answers():
			try:
				# reset the quota if allowed.
				# we do ==1 here instead of < 2 because otherwise someone could use this
				# to regain internet access after having it revoked forcefully.
				if attendance.quota_multiplier == 1:
					# create a log of this event
					if settings.RESET_EXCUSE_REQUIRED:
						excuse = reset_form.cleaned_data['excuse']
					else:
						# clear out the reset excuse if one was provided but not allowed.
						excuse = ''
					QuotaResetEvent.objects.create(event_attendance=attendance, performer=profile, excuse=excuse)

					attendance.quota_multiplier = 2
					attendance.save()

				enable_user_quota(attendance)
				sync_user_connections(profile)
			except:
				return controller_error(request)

			return HttpResponseRedirect('/quota/')
		else:
			# some answers were incorrect
			return render(request, 'frontend/reset-lecture.html', {'reset_form': reset_form, 'incorrect': True})
	else:
		reset_form = ResetLectureForm()
		return render(request, 'frontend/reset-lecture.html', {'reset_form': reset_form, 'incorrect': False})
@login_required
def quota_off(request):
	user = request.user
	profile = get_userprofile(user)
	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html')
	attendance = get_userprofile_attendance(current_event, profile)
	try:
		disable_user_quota(attendance)
	except:
		return controller_error(request)
	return HttpResponseRedirect('/quota/')

@user_passes_test(lambda u: u.has_perm('frontend.can_view_quota'))
def usage(request):
	quota_update_fail = False
	try:
		refresh_all_quota_usage()
	except:
		quota_update_fail = True

	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html')

	attendances = EventAttendance.objects.filter(event__exact=current_event).order_by('user_profile')
	total = 0L
	for a in attendances:
		total += a.quota_used

	return render(request, 'frontend/usage.html', {'attendances': attendances, 'total': bytes_str(total), 'mode': _('alphabetical'), 'quota_update_fail': quota_update_fail})


#todo: replace with generic view and roll into one function
@user_passes_test(lambda u: u.has_perm('frontend.can_view_quota'))
def usage_heavy(request):
	quota_update_fail = False
	try:
		refresh_all_quota_usage()
	except:
		quota_update_fail = True

	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html')

	attendances = EventAttendance.objects.filter(event__exact=current_event).order_by('-quota_used')
	total = 0L
	for a in attendances:
		total += a.quota_used

	return render(request, 'frontend/usage.html', {'attendances': attendances, 'total': bytes_str(total), 'mode': _('highest quota use'), 'quota_update_fail': quota_update_fail})

@user_passes_test(lambda u: u.has_perm('frontend.can_view_quota'))
def usage_speed(request):
	quota_update_fail = False
	try:
		refresh_all_quota_usage()
	except:
		quota_update_fail = True

	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html')

	attendances = list(EventAttendance.objects.filter(event__exact=current_event))
	attendances.sort(key=(lambda o: o.last_datapoint().average_speed()), reverse=True)
	total = 0L
	for a in attendances:
		total += a.quota_used

	return render(request, 'frontend/usage.html', {'attendances': attendances, 'total': bytes_str(total), 'mode': _('highest speed'), 'quota_update_fail': quota_update_fail})

@user_passes_test(lambda u: u.has_perm('frontend.can_view_quota'))
def usage_morereset(request):
	quota_update_fail = False
	try:
		refresh_all_quota_usage()
	except:
		quota_update_fail = True

	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html', {})

	attendances = EventAttendance.objects.filter(event__exact=current_event).order_by('-quota_multiplier')
	total = 0L
	for a in attendances:
		total += a.quota_used

	return render(request, 'frontend/usage.html',
		{'attendances': attendances, 'total': bytes_str(total),
		 'mode': _('most resets'), 'quota_update_fail': quota_update_fail})

@user_passes_test(lambda u: u.has_perm('frontend.can_view_quota'))
def usage_info(request, attendance_id):
	attendance = get_object_or_404(EventAttendance, id=attendance_id)

	quota_update_fail = False
	try:
		refresh_quota_usage(a)
	except:
		quota_update_fail = True
	pcs = NetworkHost.objects.filter(user_profile__exact=attendance.user_profile)

	if request.method == 'POST':
		reset_form = ResetExcuseForm(request.POST)
	else:
		reset_form = ResetExcuseForm()

	return render(request, 'frontend/usage-info.html',
		{'attendance': attendance, 'quota_update_fail': quota_update_fail, 'reset_form': reset_form}, )


@user_passes_test(lambda u: u.has_perm('frontend.can_reset_quota'))
def usage_reset(request, aid):
	a = get_object_or_404(EventAttendance, id=aid)

	if request.method != 'POST':
		return HttpResponseRedirect('/usage/' + str(aid) + '/')

	reset_form = ResetExcuseForm(request.POST)
	if not reset_form.is_valid():
		# invalid input, throw error
		return usage_info(request, aid)

	# check if I'm trying to reset quota for the current user.
	my_profile = get_userprofile(request.user)
	if a.user_profile == my_profile and a.quota_multiplier > 1:
		# current user is trying to reset their own quota, and they have already reset quota before.
		return render(request, 'frontend/cant-reset-yourself.html')

	if not a.quota_unmetered:
		# do the log event first as that's more important.
		excuse = reset_form.cleaned_data['excuse']
		QuotaResetEvent.objects.create(event_attendance=a, performer=get_userprofile(request.user), excuse=excuse)

		# now reset it.
		a.quota_multiplier += 1
		a.save()
		try:
			enable_user_quota(a)
		except:
			return controller_error(request)

	return HttpResponseRedirect('/usage/' + str(aid) + '/')

@user_passes_test(lambda u: u.has_perm('frontend.can_view_quota'))
def usage_all_on(request):
	# find all users that are in attendance this lan
	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html')

	attendances = EventAttendance.objects.filter(event__exact=current_event)
	for attendance in attendances:
		if attendance.user_profile.internet_on:
			enable_user_quota(attendance)
	return HttpResponseRedirect('/usage/')

@user_passes_test(lambda u: u.has_perm('frontend.can_view_quota'))
def usage_all_really_on(request):
	# find all users that are in attendance this lan
	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html')

	attendances = EventAttendance.objects.filter(event__exact=current_event)

	sid = transaction.savepoint()
	for attendance in attendances:
		attendance.internet_on = True
		enable_user_quota(attendance)
		attendance.save()
	transaction.savepoint_commit(sid)

	return HttpResponseRedirect('/usage/')


@user_passes_test(lambda u: u.has_perm('frontend.can_view_quota'))
def usage_all_off(request):
	# find all users that are in attendance this lan
	current_event = get_current_event()
	if current_event is None:
		return render(request, 'frontend/event-not-active.html')

	attendances = EventAttendance.objects.filter(event__exact=current_event)

	sid = transaction.savepoint()
	for attendance in attendances:
		attendance.user_profile.internet_on = False
		attendance.user_profile.save()
		disable_user_quota(attendance)
	transaction.savepoint_commit(sid)

	return HttpResponseRedirect('/usage/')

@user_passes_test(lambda u: u.has_perm('frontend.can_view_quota'))
def usage_on(request, aid):
	a = get_object_or_404(EventAttendance, id=aid)
	enable_user_quota(a)
	return HttpResponseRedirect('/usage/' + str(aid) + '/')

@user_passes_test(lambda u: u.has_perm('frontend.can_view_quota'))
def usage_off(request, aid):
	a = get_object_or_404(EventAttendance, id=aid)
	disable_user_quota(a)
	return HttpResponseRedirect('/usage/' + str(aid) + '/')

@user_passes_test(lambda u: u.has_perm('frontend.can_reset_quota'))
def usage_disable(request, aid):
	a = get_object_or_404(EventAttendance, id=aid)
	a.quota_multiplier = 0
	a.quota_unmetered = False
	a.save()
	disable_user_quota(a)
	return HttpResponseRedirect('/usage/' + str(aid) + '/')

@user_passes_test(lambda u: u.has_perm('frontend.can_view_ownership'))
def pclist(request):
	hosts = NetworkHost.objects.exclude(user_profile__exact=None).order_by('ip_address')
	return render(request, 'frontend/pclist.html', {'hosts': hosts, 'unowned': False})

@user_passes_test(lambda u: u.has_perm('frontend.can_view_ownership'))
def pclist_unowned(request):
	hosts = NetworkHost.objects.filter(user_profile__exact=None).order_by('ip_address')
	return render(request, 'frontend/pclist.html', {'hosts': hosts, 'unowned': True})

def index(request):
	theme_change_form = None
	if request.user.is_authenticated():
		theme_change_form = ThemeChangeForm({'theme': request.user.get_profile().theme})
	return render(request, 'frontend/index.html', {'theme_change_form': theme_change_form})

@login_required
def theme_change(request):
	if request.method != 'POST':
		return HttpResponseRedirect('/')

	theme_change_form = ThemeChangeForm(request.POST)

	if theme_change_form.is_valid():
		profile = request.user.get_profile()
		profile.theme = theme_change_form.cleaned_data['theme']
		profile.save()

	return HttpResponseRedirect('/')

def captive_landing(request):
	dest = ""
	if request.GET.has_key('u'):
		dest = request.GET['u']
	#if request.META.has_key('REFERER'): # as per HTTP specification, this is misspelt.
	#	dest = request.META['REFERER']

	# parse the URL, and force it to be http.
	if not dest.startswith('http://'):
		dest = ''

	# see if we can figure out why this happened

	# check if a user is signed on at this IP address
	ip = request.META['REMOTE_ADDR']
	mac = get_mac_address(ip)
	if mac == None:
		# The mac address doesn't exist
		return render(request, 'frontend/internet_login_here-failure.html')
	if settings.ONLY_CONSOLE and not is_console(mac):
		return render(request, 'frontend/not-a-console.html')


	reasons = {'reason_blacklist': False, 'reason_quota': False, 'reason_disabled': False, 'reason_sync': False, 'reason_login': False}
	try:
		h = NetworkHost.objects.get(mac_address__iexact=mac)
		if h.user_profile == None:
			raise Exception, 'no user associated with this host'

		# now get the event information
		attendance = get_attendance_currentevent(h.user_profile)

		# okay, there's active attendance
		# check quota

		if attendance.is_quota_available():
			# then there's quota

			# check if the internet access is switched on

			if h.user_profile.internet_on:
				# user is marked as online.
				# check if the host is detected as online
				if h.online:
					# host is marked as online.
					# it's probably because the site is blacklisted, suggest this
					reasons['reason_blacklist'] = True
				else:
					# host isn't marked as online
					reasons['reason_sync'] = True
			else:
				# user has internet switched off
				reasons['reason_disabled'] = True
		else:
			reasons['reason_quota'] = True
	except:
		# no active attendance, or computer not associated with a logon
		reasons['reason_login'] = True

	reasons['dest'] = dest
	reasons['f'] = LoginForm()

	return render(request, 'frontend/captive_landing.html', reasons)

@user_passes_test(lambda u: u.has_perm('frontend.can_register_attendance'))
def signin1(request):
	event = get_current_event()
	if event == None:
		messages.warning(request, 'No event is currently active.  Please make one.')
		return redirect('admin:frontend_event_add')

	if request.method == "POST":
		f = SignInForm1(request.POST)
		# validate form
		if f.is_valid():
			# look up username
			try:
				u = User.objects.get(username__iexact=f.cleaned_data['username'])
			except ObjectDoesNotExist:
				# username doesn't exist, lets create.
				return render(
					request,
					'frontend/signin2.html',
					dict(
						form=SignInForm2(
							initial=dict(username=f.cleaned_data['username'])
						)
					),
				)
			else:
				# username exists, skip to step 3
				return redirect('signin3', u.id)

		# not valid, fall through.

	else:
		f = SignInForm1()

	return render(request, 'frontend/signin1.html', dict(form=f))


@user_passes_test(lambda u: u.has_perm('frontend.can_signin'))
def signin2(request):
	event = get_current_event()
	if event == None:
		messages.warning(request, 'No event is currently active.  Please make one.')
		return redirect('admin:frontend_event_add')

	if request.method == 'POST':
		f = SignInForm2(request.POST)
		if f.is_valid():
			# check to make sure that user doesn't exist
			if User.objects.filter(username__iexact=f.cleaned_data['username']).exists():
				# fail out, the username exist
				messages.error(request, 'That username already exists.')
			else:
				# the user doesn't exist, create it.
				u = User(
					username=f.cleaned_data['username'],
					first_name=f.cleaned_data['first_name'],
					last_name=f.cleaned_data['last_name']
				)

				# set a password
 				password = ''.join([random.choice('0123456789bcfghjklmnpqrstvwxyz') for i in range(8)])
				u.set_password(password)

				messages.success(request, _('Generated password for user: %s') % password)
				messages.info(request, _('Please inform the user to change their password after logging in.'))
				u.save()

				# create matching userprofile
				UserProfile(user=u).save()

				# now go to next step
				return redirect('signin3', u.id)

	else:
		return redirect('signin')

	return render(request, 'frontend/signin2.html', dict(form=f))

@user_passes_test(lambda u: u.has_perm('frontend.can_register_attendance'))
def signin3(request, uid):
	u = get_object_or_404(User, id=uid)

	current_event = get_current_event()
	if current_event == None:
		messages.warning(request, 'No event is currently active.  Please make one.')
		return redirect('admin:frontend_event_add')

	if has_userprofile_attended(current_event, u.get_profile()):
		# see if the user is already signed in.
		# if so, direct them back to the start.
		messages.error(request, 'That user has already been signed in for this event.')

		# return them to the signin start page
		return redirect('signin')

	if request.method == 'POST':
		f = SignInForm3(request.POST)
		if f.is_valid():
			# create an attendance!

			if f.cleaned_data['quota_unlimited']:
				# create unmetered attendance
				a = EventAttendance(quota_unmetered=True, event=current_event, user_profile=u.get_profile(), registered_by=request.user.get_profile())
			else:
				a = EventAttendance(quota_amount=f.cleaned_data['quota_amount']*1048576, event=current_event, user_profile=u.get_profile(), registered_by=request.user.get_profile())

			a.save()

			# now sync user connections
			enable_user_quota(a)

			# attendance created, go back to signin page
			messages.success(request, 'Attendance registered, and enabled internet access for user.')
			return redirect('signin')
	else:
		f = SignInForm3()

	return render(request, 'frontend/signin3.html', dict(form=f, u=u))


def ip4portforward_toggle(request, object_id):
	portforward = get_object_or_404(IP4PortForward, id=object_id)
	if request.method == 'POST':
		portforward.enabled = not portforward.enabled
		portforward.save()
	return redirect('ip4portforward_list')

def ip4portforward_forceapply(request):
	if request.method == 'POST':
		apply_ip4portforwards()
	return redirect('ip4portforward_list')