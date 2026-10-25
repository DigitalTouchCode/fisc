from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from fiscguy.checks import fiscguy_security_checks
from fiscguy.models import AuditLog, Certs, Device

PASSWORD = "correct-horse-battery"
KEY_MARKER = "SUPERSECRETKEYMARKER"
URLCONF = "fiscguy.tests.web_urls"


def make_device(**kwargs):
    defaults = dict(
        org_name="Mine",
        activation_key="act-key",
        device_id="41872",
        device_model_name="Server",
        device_model_version="1.0",
        device_serial_number="SN",
    )
    defaults.update(kwargs)
    return Device.objects.create(**defaults)


def make_user(username, *codenames, superuser=False):
    user = get_user_model().objects.create_user(username, password=PASSWORD)
    if superuser:
        user.is_superuser = True
        user.save()
    for codename in codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename, content_type__app_label="fiscguy"))
    return user


@override_settings(ROOT_URLCONF=URLCONF, FISCGUY_UI_ENABLED=True)
class WebAccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.device = make_device()
        self.viewer = make_user("viewer", "view_receipts")
        self.client = Client()

    def test_ui_is_off_unless_enabled(self):
        self.client.force_login(self.viewer)
        with override_settings(FISCGUY_UI_ENABLED=False):
            self.assertEqual(self.client.get("/ui/").status_code, 404)

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get("/ui/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_logged_in_user_without_permission_is_refused(self):
        self.client.force_login(make_user("nobody"))
        self.assertEqual(self.client.get("/ui/").status_code, 403)

    def test_permitted_user_sees_dashboard_with_security_headers(self):
        self.client.force_login(self.viewer)
        response = self.client.get("/ui/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["X-Frame-Options"], "DENY")

    def test_view_permission_does_not_allow_closing_a_day(self):
        self.client.force_login(self.viewer)
        response = self.client.post(f"/ui/devices/{self.device.pk}/close-day/")
        self.assertEqual(response.status_code, 403)

    def test_actions_are_post_only(self):
        self.client.force_login(make_user("closer", "close_day"))
        self.assertEqual(self.client.get(f"/ui/devices/{self.device.pk}/close-day/").status_code, 405)

    def test_post_without_csrf_token_is_rejected(self):
        closer = make_user("closer", "close_day")
        client = Client(enforce_csrf_checks=True)
        client.force_login(closer)
        response = client.post(f"/ui/devices/{self.device.pk}/open-day/")
        self.assertEqual(response.status_code, 403)

    @patch("fiscguy.web.views.ConfigurationService")
    @patch("fiscguy.web.views.OpenDayService")
    def test_open_day_is_audited(self, MockOpen, MockConfig):
        self.client.force_login(make_user("closer", "close_day"))
        response = self.client.post(f"/ui/devices/{self.device.pk}/open-day/")
        self.assertEqual(response.status_code, 302)
        entry = AuditLog.objects.get(action="open_day")
        self.assertEqual(entry.actor_name, "closer")
        self.assertEqual(entry.device_ref, "41872")

    def test_device_detail_never_shows_key_material(self):
        Certs.objects.create(device=self.device, csr="csr", certificate="cert", certificate_key=KEY_MARKER)
        self.client.force_login(self.viewer)
        for url in ("/ui/", f"/ui/devices/{self.device.pk}/"):
            self.assertNotContains(self.client.get(url), KEY_MARKER)
            self.assertNotContains(self.client.get(url), "act-key")

    @override_settings(FISCGUY_DEVICE_QUERYSET="fiscguy.tests.web_urls.only_mine")
    def test_host_scope_hides_other_devices(self):
        other = make_device(org_name="Theirs", device_id="99999")
        self.client.force_login(make_user("closer", "view_receipts", "close_day"))
        self.assertEqual(self.client.get(f"/ui/devices/{self.device.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/ui/devices/{other.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/ui/devices/{other.pk}/close-day/").status_code, 404)

    @override_settings(FISCGUY_ACCESS_CHECK=lambda request, action: action == "view_receipts")
    def test_host_access_check_replaces_default_permissions(self):
        self.client.force_login(make_user("nobody"))
        self.assertEqual(self.client.get("/ui/").status_code, 200)
        self.assertEqual(self.client.get("/ui/audit/").status_code, 403)


@override_settings(ROOT_URLCONF=URLCONF, FISCGUY_UI_ENABLED=True)
class ReauthAndRegistrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.manager = make_user("manager", "manage_device")
        self.client = Client()
        self.client.force_login(self.manager)

    def test_registration_requires_recent_password_confirmation(self):
        response = self.client.get("/ui/devices/register/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/ui/reauth/", response["Location"])

    def test_correct_password_unlocks_registration(self):
        response = self.client.post(
            "/ui/reauth/", {"password": PASSWORD, "next": "/ui/devices/register/"}
        )
        self.assertRedirects(response, "/ui/devices/register/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/ui/devices/register/").status_code, 200)

    def test_reauth_does_not_redirect_off_site(self):
        response = self.client.post("/ui/reauth/", {"password": PASSWORD, "next": "https://evil.example/"})
        self.assertEqual(response["Location"], "/ui/")

    def test_wrong_password_is_audited_and_throttled(self):
        for _ in range(5):
            self.client.post("/ui/reauth/", {"password": "wrong", "next": ""})
        response = self.client.post("/ui/reauth/", {"password": PASSWORD, "next": ""})
        self.assertContains(response, "Too many attempts")
        self.assertTrue(AuditLog.objects.filter(action="reauth_failed").exists())

    def test_failed_upload_does_not_echo_the_private_key_or_activation_key(self):
        self.client.post("/ui/reauth/", {"password": PASSWORD, "next": ""})
        response = self.client.post(
            "/ui/devices/register/manual/",
            {
                "org_name": "",
                "device_id": "abc",
                "private_key_text": KEY_MARKER,
                "activation_key": "act-secret-123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, KEY_MARKER)
        self.assertNotContains(response, "act-secret-123")

    def test_garbage_certificate_is_rejected_without_leaking_the_key(self):
        self.client.post("/ui/reauth/", {"password": PASSWORD, "next": ""})
        response = self.client.post(
            "/ui/devices/register/manual/",
            {
                "org_name": "Org",
                "device_id": "41872",
                "model_name": "Server",
                "model_version": "1",
                "certificate_text": "not a certificate",
                "private_key_text": KEY_MARKER,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, KEY_MARKER)
        self.assertFalse(Device.objects.exists())


class ApiPermissionTests(TestCase):
    @override_settings(
        ROOT_URLCONF=URLCONF,
        FISCGUY_PERMISSION_CLASSES=["rest_framework.permissions.IsAdminUser"],
    )
    def test_api_denies_anonymous_and_non_staff_by_default(self):
        make_device()
        self.assertIn(Client().get("/receipts/").status_code, (401, 403))
        user = make_user("plain")
        client = Client()
        client.force_login(user)
        self.assertIn(client.get("/receipts/").status_code, (401, 403))

    def test_encryption_key_warning(self):
        with override_settings(FISCGUY_ENCRYPTION_KEY=None):
            self.assertIn("fiscguy.W001", [m.id for m in fiscguy_security_checks(None)])
        with override_settings(FISCGUY_ENCRYPTION_KEY="x" * 44):
            self.assertNotIn("fiscguy.W001", [m.id for m in fiscguy_security_checks(None)])
