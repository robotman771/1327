import datetime

from django.contrib.auth.models import Group
from django.db import transaction
from django.template.defaultfilters import floatformat
from django.test import TestCase
from django.urls import reverse
from django_webtest import WebTest
from guardian.shortcuts import assign_perm, get_perms
from guardian.utils import get_anonymous_user
from model_bakery import baker
from reversion import revisions
from reversion.models import Version

from _1327.polls.models import Choice, Poll
from _1327.user_management.models import UserProfile


class PollModelTests(TestCase):

	def test_percentage(self):
		num_votes = 10
		num_choices = 3
		num_participants = 5

		user = baker.make(UserProfile, _quantity=num_participants)
		poll = baker.make(Poll, participants=user)

		baker.make(Choice, poll=poll, _quantity=num_choices, votes=num_votes)

		expected_percentage = num_votes * 100 / num_participants
		for choice in poll.choices.all():
			self.assertAlmostEqual(choice.percentage(), expected_percentage, 2)

	def test_percentage_with_no_participants(self):
		poll = baker.make(Poll)

		num_choices = 3
		baker.make(Choice, poll=poll, _quantity=num_choices, votes=0)

		expected_percentage = 0
		for choice in poll.choices.all():
			self.assertAlmostEqual(choice.percentage(), expected_percentage, 2)


class PollViewTests(WebTest):
	csrf_checks = False

	@classmethod
	def setUpTestData(cls):
		cls.user = baker.make(UserProfile, is_superuser=True)
		cls.poll = baker.make(
			Poll,
			start_date=datetime.date.today(),
			end_date=datetime.date.today() + datetime.timedelta(days=3),
		)
		baker.make(
			Choice,
			poll=cls.poll,
			_quantity=3,
		)
		cls.group = baker.make(Group)
		cls.poll.set_all_permissions(cls.group)
		cls.user.groups.add(cls.group)
		assign_perm("polls.add_poll", cls.group)

	def test_view_all_running_poll_with_insufficient_permissions(self):
		response = self.app.get(reverse('polls:index'))
		self.assertEqual(response.status_code, 200)
		self.assertIn(b"There are no polls you can vote for.", response.body)
		self.assertIn(b"There are no results you can see.", response.body)

	def test_view_all_running_poll_with_sufficient_permissions(self):
		response = self.app.get(reverse('polls:index'), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertIn(self.poll.title_en.encode('utf-8'), response.body)
		self.assertIn(b"There are no results you can see.", response.body)

	def test_view_all_running_and_not_running(self):
		finished_poll = baker.make(
			Poll,
			start_date=datetime.date.today() - datetime.timedelta(days=10),
			end_date=datetime.date.today() - datetime.timedelta(days=1),
		)

		response = self.app.get(reverse('polls:index'), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertIn(self.poll.title_en.encode('utf-8'), response.body)
		self.assertIn(finished_poll.title.encode('utf-8'), response.body)

	def test_view_all_already_participated(self):
		self.poll.participants.add(self.user)
		self.poll.save()

		response = self.app.get(reverse('polls:index'), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertIn(b"There are no polls you can vote for.", response.body)
		self.assertIn(self.poll.title_en.encode('utf-8'), response.body)

	def test_view_all_future_poll(self):
		self.poll.start_date += datetime.timedelta(days=1)
		self.poll.save()

		response = self.app.get(reverse('polls:index'))
		self.assertEqual(response.status_code, 200)
		self.assertIn(b"There are no polls you can vote for.", response.body)
		self.assertIn(b"There are no results you can see.", response.body)

		response = self.app.get(reverse('polls:index'), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertIn(b"Upcoming polls", response.body)
		self.assertIn(b"There are no polls you can vote for.", response.body)
		self.assertIn(b"There are no results you can see.", response.body)

	def test_create_poll(self):
		response = self.app.get(reverse('documents:create', args=['poll']), user=self.user)
		self.assertEqual(response.status_code, 200)

		form = response.forms['document-form']
		form['choices-0-description_en'] = 'test description'
		form['choices-0-index'] = 0
		form['choices-0-text_en'] = 'test choice'
		form['choices-0-text_de'] = 'test choice de'
		form['choices-1-description_en'] = 'test description 2'
		form['choices-1-index'] = 1
		form['choices-1-text_en'] = 'test choice 2'
		form['choices-1-text_de'] = 'test choice 2 de'
		form['title_en'] = 'TestPoll'
		form['text_en'] = 'Sample Text'
		form['max_allowed_number_of_answers'] = 1
		form['start_date'] = '2016-01-01'
		form['end_date'] = '2088-01-01'
		form['comment'] = 'sample comment'
		form['group'] = self.group.pk

		self.assertFalse("Hidden" in str(form.fields['vote_groups'][0]))

		response = form.submit()
		self.assertEqual(response.status_code, 302)

		poll = Poll.objects.get(title_en='TestPoll')
		self.assertEqual(poll.choices.count(), 2)

	def test_group_field_hidden_when_user_has_one_group(self):
		response = self.app.get(reverse('documents:create', args=['poll']), user=self.user)
		self.assertEqual(response.status_code, 200)

		form = response.forms['document-form']
		self.assertTrue("Hidden" in str(form.fields['group'][0]))

	def test_group_field_not_hidden_when_user_has_multiple_groups(self):
		other_group = baker.make(Group)
		self.user.groups.add(other_group)
		assign_perm("polls.add_poll", other_group)
		response = self.app.get(reverse('documents:create', args=['poll']), user=self.user)
		self.assertEqual(response.status_code, 200)

		form = response.forms['document-form']
		self.assertFalse("Hidden" in str(form.fields['group'][0]))

	def test_create_poll_with_permissions(self):
		response = self.app.get(reverse('documents:create', args=['poll']), user=self.user)
		self.assertEqual(response.status_code, 200)

		form = response.forms['document-form']
		form['choices-0-description_en'] = 'test description'
		form['choices-0-index'] = 0
		form['choices-0-text_en'] = 'test choice'
		form['choices-0-text_de'] = 'test choice de'
		form['choices-1-description_en'] = 'test description 2'
		form['choices-1-index'] = 1
		form['choices-1-text_en'] = 'test choice 2'
		form['choices-1-text_de'] = 'test choice 2 de'
		form['title_en'] = 'TestPoll'
		form['text_en'] = 'Sample Text'
		form['max_allowed_number_of_answers'] = 1
		form['start_date'] = '2016-01-01'
		form['end_date'] = '2088-01-01'
		form['comment'] = 'sample comment'
		form['group'] = self.group.pk
		form['vote_groups'] = [self.group.pk]

		response = form.submit()
		self.assertEqual(response.status_code, 302)

		poll = Poll.objects.get(title_en='TestPoll')
		self.assertEqual(poll.choices.count(), 2)
		group_permissions = ["polls.{}".format(name) for name in get_perms(self.group, poll)]
		self.assertEqual(len(group_permissions), 5)
		self.assertIn(poll.edit_permission_name, group_permissions)
		self.assertIn(poll.vote_permission_name, group_permissions)
		self.assertIn(poll.view_permission_name, group_permissions)
		self.assertIn(poll.delete_permission_name, group_permissions)

	def test_create_poll_user_has_no_permission(self):
		user = baker.make(UserProfile)

		response = self.app.get(reverse('documents:create', args=['poll']), user=user, expect_errors=True)
		self.assertEqual(response.status_code, 403)

		response = self.app.post(reverse('documents:create', args=['poll']), user=user, expect_errors=True)
		self.assertEqual(response.status_code, 403)

	def test_edit_poll(self):
		response = self.app.get(reverse(self.poll.get_edit_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)

		choice_text_en = 'test choice'
		choice_text_de = 'test choice de'
		choice_description_en = 'test description'
		poll_title = 'Title'
		poll_description = 'Description'

		form = response.forms['document-form']
		form['choices-3-description_en'] = choice_description_en
		form['choices-3-index'] = 3
		form['choices-3-text_en'] = choice_text_en
		form['choices-3-text_de'] = choice_text_de
		form['choices-0-text_en'] = choice_text_en
		form['choices-0-text_de'] = choice_text_de
		form['title_en'] = poll_title
		form['text_en'] = poll_description
		form['comment'] = 'sample comment'

		self.assertTrue("Hidden" in str(form.fields['vote_groups'][0]))

		response = form.submit()
		self.assertEqual(response.status_code, 302)

		poll = Poll.objects.get(id=self.poll.id)
		self.assertEqual(poll.title_en, poll_title)
		self.assertEqual(poll.text_en, poll_description)
		self.assertEqual(poll.choices.count(), 4)
		self.assertEqual(poll.choices.first().text_en, choice_text_en)
		self.assertEqual(poll.choices.first().text_de, choice_text_de)
		self.assertEqual(poll.choices.last().text_en, choice_text_en)
		self.assertEqual(poll.choices.last().text_de, choice_text_de)
		self.assertEqual(poll.choices.last().description_en, choice_description_en)

	def test_edit_poll_delete_choice(self):
		response = self.app.get(reverse(self.poll.get_edit_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)

		form = response.forms['document-form']
		form['title_en'] = 'title'
		form['choices-0-DELETE'] = True
		form['comment'] = 'sample comment'

		response = form.submit()
		self.assertEqual(response.status_code, 302)

		poll = Poll.objects.get(id=self.poll.id)
		self.assertEqual(poll.choices.count(), 2)

	def test_edit_poll_user_has_no_permission(self):
		user = baker.make(UserProfile)

		response = self.app.get(reverse(self.poll.get_edit_url_name(), args=[self.poll.url_title]), user=user, expect_errors=True)
		self.assertEqual(response.status_code, 403)

		response = self.app.post(reverse(self.poll.get_edit_url_name(), args=[self.poll.url_title]), user=user, expect_errors=True)
		self.assertEqual(response.status_code, 403)

	def test_deletion_no_superuser(self):
		user = baker.make(UserProfile)
		assign_perm(self.poll.edit_permission_name, user, self.poll)

		response = self.app.get(reverse('documents:get_delete_cascade', args=[self.poll.url_title]), user=user)
		self.assertIn(self.poll.title, response.body.decode('utf-8'))

		response = self.app.get(reverse('documents:delete_document', args=[self.poll.url_title]), user=user)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(Poll.objects.count(), 0)

	def test_no_description_column_if_no_description(self):
		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertNotIn("Description", response.body.decode('utf-8'))
		choice = self.poll.choices.first()
		choice.description_en = "test"
		choice.save()
		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertIn("Description", response.body.decode('utf-8'))

	def test_result_preview_button_for_superusers(self):
		response = self.app.get(reverse('polls:index'), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertIn("fa fa-eye", response.body.decode('utf-8'))

		user = baker.make(UserProfile)
		assign_perm(self.poll.vote_permission_name, user, self.poll)
		response = self.app.get(reverse('polls:index'), user=user)
		self.assertEqual(response.status_code, 200)
		self.assertNotIn("fa fa-eye", response.body.decode('utf-8'))

	def test_result_preview_non_superuser(self):
		user = baker.make(UserProfile)
		assign_perm(self.poll.vote_permission_name, user, self.poll)

		response = self.app.get(reverse('polls:results_for_admin', args=[self.poll.url_title]), user=user, expect_errors=True)
		self.assertEqual(response.status_code, 403)

	def test_result_preview_superuser(self):
		response = self.app.get(reverse('polls:results_for_admin', args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)

	def test_view_poll_list_as_student_without_vote_permission_but_view_permission_by_anonymous(self):
		# 1. create a new poll and give anonymous view permission
		poll = baker.make(
			Poll,
			start_date=datetime.date.today(),
			end_date=datetime.date.today() + datetime.timedelta(days=3),
		)
		baker.make(
			Choice,
			poll=poll,
			_quantity=3,
		)

		assign_perm(poll.view_permission_name, get_anonymous_user(), poll)

		# 2. create a student, add him to the student group and let him have a look at the polls index page
		student = baker.make(UserProfile)
		student_group = Group.objects.get(name='Student')
		student.groups.add(student_group)

		response = self.app.get(reverse('polls:index'), user=student)
		self.assertEqual(response.status_code, 200)
		self.assertIn(poll.title, response.body.decode('utf-8'))


class PollResultTests(WebTest):
	csrf_checks = False

	@classmethod
	def setUpTestData(cls):
		cls.user = baker.make(UserProfile)
		cls.poll = baker.make(
			Poll,
			start_date=datetime.date.today(),
			end_date=datetime.date.today() + datetime.timedelta(days=3),
		)
		baker.make(
			Choice,
			poll=cls.poll,
			votes=10,
			_quantity=3,
		)

	def setUp(self):
		self.user.refresh_from_db()
		self.poll.refresh_from_db()

	def assign_vote_perm(self, user, obj):
		assign_perm('polls.{vote}'.format(vote=Poll.VOTE_PERMISSION_NAME), user, obj)
		user.save()

	def assign_view_perm(self, user, obj):
		assign_perm('polls.{view}'.format(view=Poll.VIEW_PERMISSION_NAME), user, obj)
		user.save()

	def assign_view_vote_perms(self, user, obj):
		self.assign_view_perm(user, obj)
		self.assign_vote_perm(user, obj)

	def test_view_with_insufficient_permissions(self):
		response = self.app.get(
			reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]),
			expect_errors=True,
			user=self.user,
		)
		self.assertEqual(response.status_code, 403)

	def test_view_result_without_vote(self):
		self.assign_view_vote_perms(self.user, self.poll)
		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertTemplateUsed(response, 'polls_vote.html')

	def test_view_after_vote(self):
		self.assign_view_vote_perms(self.user, self.poll)
		self.poll.participants.add(self.user)

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'polls_results.html')

		for choice in self.poll.choices.all():
			self.assertIn(choice.text.encode('utf-8'), response.body)
			self.assertIn(floatformat(choice.percentage()).encode('utf-8'), response.body)
			self.assertIn(str(choice.votes).encode('utf-8'), response.body)

	def test_view_with_description_of_poll(self):
		self.assign_view_vote_perms(self.user, self.poll)
		self.poll.text_en = b"a nice description"
		self.poll.participants.add(self.user)
		self.poll.save()

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertIn(self.poll.text_en, response.body)

	def test_view_before_poll_has_started(self):
		self.assign_view_vote_perms(self.user, self.poll)
		self.poll.start_date += datetime.timedelta(weeks=1)
		self.poll.save()

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'polls_index.html')

	def test_view_poll_without_vote_permission(self):
		self.assign_view_perm(self.user, self.poll)

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user, expect_errors=True)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'polls_results.html')

	def test_vote_poll_without_vote_permission(self):
		self.assign_view_perm(self.user, self.poll)

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user, expect_errors=True)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'polls_results.html')


class PollVoteTests(WebTest):
	csrf_checks = False

	@classmethod
	def setUpTestData(cls):
		cls.user = baker.make(UserProfile, is_superuser=True)
		cls.poll = baker.make(
			Poll,
			start_date=datetime.date.today(),
			end_date=datetime.date.today() + datetime.timedelta(days=3),
		)
		baker.make(
			Choice,
			poll=cls.poll,
			votes=10,
			_quantity=3,
		)

	def setUp(self):
		self.user.refresh_from_db()
		self.poll.refresh_from_db()

	def test_vote_with_insufficient_permissions(self):
		user_without_perms = baker.make(UserProfile)
		response = self.app.get(
			reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]),
			expect_errors=True,
			user=user_without_perms,
		)
		self.assertEqual(response.status_code, 403)

		user = baker.make(UserProfile)
		assign_perm(Poll.VIEW_PERMISSION_NAME, user, self.poll)

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=user, expect_errors=True)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'polls_results.html')

	def test_vote_with_sufficient_permissions(self):
		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)

		user = baker.make(UserProfile)
		assign_perm(Poll.VIEW_PERMISSION_NAME, user, self.poll)
		assign_perm('vote_poll', user, self.poll)
		user.save()
		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=user)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'polls_vote.html')

	def test_vote_poll_finished(self):
		self.poll.end_date = datetime.date.today() - datetime.timedelta(days=1)
		self.poll.save()

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertTemplateUsed(response, 'polls_results.html')

	def test_vote_poll_already_voted(self):
		self.poll.participants.add(self.user)
		self.poll.save()

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertTemplateUsed(response, 'polls_results.html')
		response = self.app.post(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertTemplateUsed(response, 'polls_results.html')

	def test_start_vote_multiple_choice_poll(self):
		self.poll.max_allowed_number_of_answers = 2
		self.poll.save()

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]) + '/', user=self.user)
		self.assertEqual(response.status_code, 301)

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertIn(b"checkbox", response.body)
		self.assertNotIn(b"radio", response.body)

	def test_start_vote_single_choice_poll(self):
		self.poll.max_allowed_number_of_answers = 1
		self.poll.save()

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertIn(b"radio", response.body)
		self.assertNotIn(b"checkbox", response.body)

	def test_choices_in_response(self):
		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		for choice in self.poll.choices.all():
			self.assertIn(choice.text.encode('utf-8'), response.body)

	def test_vote_without_submitting_a_choice(self):
		response = self.app.post(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertRedirects(response, reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]))

	def test_vote_single_choice_submitting_more_than_one_choice(self):
		self.poll.max_allowed_number_of_answers = 1
		self.poll.save()

		data = [('choice', choice.id) for choice in self.poll.choices.all()]

		response = self.app.post(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), params=data, user=self.user)
		self.assertRedirects(response, reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]))

	def test_vote_single_choice_correctly(self):
		self.poll.max_allowed_number_of_answers = 1
		self.poll.save()

		choice = self.poll.choices.first()
		data = [('choice', choice.id)]
		votes = choice.votes

		response = self.app.post(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), params=data, user=self.user)
		self.assertEqual(response.status_code, 302)

		choice = self.poll.choices.first()
		self.assertEqual(choice.votes, votes + 1)
		self.assertEqual(self.poll.participants.count(), 1)

		response = response.follow()
		self.assertTemplateUsed(response, 'polls_results.html')

	def test_vote_multiple_choice_correctly(self):
		self.poll.max_allowed_number_of_answers = self.poll.choices.count()
		self.poll.save()
		data = []
		votes = []
		for choice in self.poll.choices.all():
			data.append(('choice', choice.id))
			votes.append(choice.votes)

		response = self.app.post(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), params=data, user=self.user)
		self.assertEqual(response.status_code, 302)
		for i, choice in enumerate(self.poll.choices.all()):
			self.assertEqual(choice.votes, votes[i] + 1)

		self.assertEqual(self.poll.participants.count(), 1)
		response = response.follow()
		self.assertTemplateUsed(response, 'polls_results.html')

	def test_view_before_poll_has_started(self):
		self.poll.start_date += datetime.timedelta(weeks=1)
		self.poll.save()

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'polls_index.html')

	def test_view_poll_before_end(self):
		self.poll.participants.add(self.user)
		self.poll.show_results_immediately = True
		self.poll.save()

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'polls_results.html')

		self.poll.show_results_immediately = False
		self.poll.save()

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertRedirects(response, reverse('polls:index'))

	def test_vote_poll_with_results_that_can_not_be_seen_immediately(self):
		self.poll.show_results_immediately = False
		self.poll.save()

		response = self.app.get(reverse(self.poll.get_view_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'polls_vote.html')

		form = response.form
		form['choice'] = self.poll.choices.first().pk

		response = form.submit()
		self.assertRedirects(response, reverse('polls:index'))


class PollEditTests(WebTest):
	csrf_checks = False

	@classmethod
	def setUpTestData(cls):
		cls.user = baker.make(UserProfile, is_superuser=True)
		cls.poll = baker.make(
			Poll,
			title_en='title',
			start_date=datetime.date.today(),
			end_date=datetime.date.today() + datetime.timedelta(days=3),
		)
		baker.make(
			Choice,
			poll=cls.poll,
			votes=10,
			_quantity=3,
		)
		cls.group = baker.make(Group)
		cls.poll.set_all_permissions(cls.group)
		cls.user.groups.add(cls.group)
		assign_perm("polls.add_poll", cls.group)

	def test_create_two_polls_without_changing_url_title(self):
		response = self.app.get(reverse('documents:create', args=['poll']), user=self.user)
		self.assertEqual(response.status_code, 200)

		form = response.forms['document-form']
		form['title_en'] = 'new awesome title'
		form['choices-0-text_en'] = 'test choice'
		form['choices-1-text_en'] = 'test choice 2'
		form['choices-0-text_de'] = 'test choice de'
		form['choices-1-text_de'] = 'test choice 2 de'
		form['text_en'] = 'Description'
		form['comment'] = 'sample comment'
		form['group'] = self.group.pk
		response = form.submit().follow()
		self.assertEqual(response.status_code, 200)
		self.assertEqual(Poll.objects.count(), 2)

		response = self.app.get(reverse('documents:create', args=['poll']), user=self.user)
		self.assertEqual(response.status_code, 200)

	def test_submit_with_too_few_forms(self):
		response = self.app.get(reverse(self.poll.get_edit_url_name(), args=[self.poll.url_title]) + '/', user=self.user)
		self.assertEqual(response.status_code, 301)

		response = self.app.get(reverse(self.poll.get_edit_url_name(), args=[self.poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)

		form = response.forms['document-form']
		form['comment'] = 'sample comment'
		form['choices-0-DELETE'] = True
		form['choices-1-DELETE'] = True
		form['choices-2-DELETE'] = True

		response = form.submit()
		self.assertTemplateUsed(response, 'polls_edit.html')
		self.assertEqual(Choice.objects.filter(poll=self.poll).count(), 3)

		form = response.forms['document-form']
		form['comment'] = 'sample comment'
		form['choices-0-DELETE'] = True
		form['choices-1-DELETE'] = True
		form['choices-2-DELETE'] = False

		response = form.submit()
		self.assertTemplateUsed(response, 'polls_edit.html')
		self.assertEqual(Choice.objects.filter(poll=self.poll).count(), 3)

	def test_submit_with_sufficient_forms(self):
		response = self.app.get(reverse(self.poll.get_edit_url_name(), args=[self.poll.url_title]), user=self.user)

		form = response.forms['document-form']
		form['comment'] = 'sample comment'
		form['choices-0-DELETE'] = True
		form['choices-1-DELETE'] = False
		form['choices-2-DELETE'] = False

		form.submit()
		self.assertEqual(Choice.objects.filter(poll=self.poll).count(), 2)

	def test_submit_more_forms(self):
		response = self.app.get(reverse(self.poll.get_edit_url_name(), args=[self.poll.url_title]), user=self.user)

		form = response.forms['document-form']
		form['comment'] = 'sample comment'
		form['choices-3-text_en'] = 'choice 4'
		form['choices-3-text_de'] = 'choice 4 de'

		form.submit()
		self.assertEqual(Choice.objects.filter(poll=self.poll).count(), 4)


class PollRevertionTests(WebTest):
	csrf_checks = False
	extra_environ = {'HTTP_ACCEPT_LANGUAGE': 'en'}

	@classmethod
	def setUpTestData(cls):
		cls.user = baker.make(UserProfile, is_superuser=True)

		cls.poll = baker.prepare(Poll, text_en='text', start_date=datetime.date.today(), end_date=datetime.date.today())
		with transaction.atomic(), revisions.create_revision():
			cls.poll.save()
			revisions.set_user(cls.user)
			revisions.set_comment('test version')

		cls.poll.text_en = 'very goood and nice text'
		with transaction.atomic(), revisions.create_revision():
			cls.poll.save()
			revisions.set_user(cls.user)
			revisions.set_comment('change text')

	def test_revert_poll_no_votes(self):
		poll = Poll.objects.get()
		self.assertTrue(poll.can_be_reverted)
		versions = Version.objects.get_for_object(poll)
		self.assertEqual(len(versions), 2)

		response = self.app.post(
			reverse('documents:revert') + '/',
			params={'id': versions[1].pk, 'url_title': poll.url_title},
			user=self.user,
			xhr=True
		)
		self.assertEqual(response.status_code, 301)

		response = self.app.post(
			reverse('documents:revert'),
			params={'id': versions[1].pk, 'url_title': poll.url_title},
			user=self.user,
			xhr=True
		)
		self.assertEqual(response.status_code, 200)

		versions = Version.objects.get_for_object(poll)
		self.assertEqual(len(versions), 3)

		response = self.app.get(reverse('versions', args=[poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertNotIn('This Document can not be reverted!', response.body.decode('utf-8'))

	def test_revert_poll_after_vote(self):
		poll = Poll.objects.get()

		self.assertTrue(poll.can_be_reverted)
		poll.participants.add(self.user)
		self.assertFalse(poll.can_be_reverted)

		versions = Version.objects.get_for_object(poll)
		self.assertEqual(len(versions), 2)

		response = self.app.post(
			reverse('documents:revert') + '/',
			params={'id': versions[1].pk, 'url_title': poll.url_title},
			user=self.user,
			xhr=True
		)
		self.assertEqual(response.status_code, 301)

		response = self.app.post(
			reverse('documents:revert'),
			params={'id': versions[1].pk, 'url_title': poll.url_title},
			user=self.user,
			xhr=True,
			status=400
		)
		self.assertEqual(response.status_code, 400)

		new_versions = Version.objects.get_for_object(poll)
		self.assertEqual(len(versions), len(new_versions))

		response = self.app.get(reverse('versions', args=[poll.url_title]), user=self.user)
		self.assertEqual(response.status_code, 200)
		self.assertIn('This Document can not be reverted!', response.body.decode('utf-8'))
