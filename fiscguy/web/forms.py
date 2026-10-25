from django import forms

MAX_PEM_BYTES = 64 * 1024


class WriteOnlyTextarea(forms.Textarea):
    """Never echoes its value back into the page, even when the form is re-rendered with errors."""

    def format_value(self, value):
        return None


class ReauthForm(forms.Form):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}), label="Your password"
    )


class DeviceDetailsForm(forms.Form):
    org_name = forms.CharField(max_length=255, label="Organisation name")
    device_id = forms.RegexField(r"^\d{1,100}$", label="Device ID", error_messages={"invalid": "Digits only."})
    device_sn = forms.CharField(max_length=255, label="Device serial number", required=False)
    model_name = forms.CharField(max_length=255, label="Device model name")
    model_version = forms.CharField(max_length=255, label="Device model version")
    production = forms.BooleanField(required=False, label="Production environment")
    confirm_text = forms.CharField(
        required=False,
        label="Confirm reset",
        help_text="Only when switching test/production on an existing device: type the device ID.",
    )

    def confirm_reset(self) -> bool:
        data = self.cleaned_data
        return bool(data.get("confirm_text")) and data["confirm_text"].strip() == data["device_id"]


class ApiRegistrationForm(DeviceDetailsForm):
    device_sn = forms.CharField(max_length=255, label="Device serial number")
    activation_key = forms.CharField(
        max_length=255,
        label="Activation key",
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
    )


class ManualRegistrationForm(DeviceDetailsForm):
    activation_key = forms.CharField(
        max_length=255,
        required=False,
        label="Activation key (optional)",
        widget=forms.PasswordInput(render_value=False, attrs={"autocomplete": "off"}),
    )
    certificate_file = forms.FileField(required=False, label="Certificate file (.pem/.crt)")
    certificate_text = forms.CharField(
        required=False,
        label="or paste the certificate",
        widget=WriteOnlyTextarea(attrs={"rows": 6, "autocomplete": "off", "spellcheck": "false"}),
    )
    private_key_file = forms.FileField(required=False, label="Private key file (.key/.pem)")
    private_key_text = forms.CharField(
        required=False,
        label="or paste the private key",
        widget=WriteOnlyTextarea(attrs={"rows": 6, "autocomplete": "off", "spellcheck": "false"}),
    )

    def _read(self, upload_name: str, text_name: str) -> str:
        upload = self.cleaned_data.get(upload_name)
        if upload:
            if upload.size > MAX_PEM_BYTES:
                raise forms.ValidationError({upload_name: "That file is too large to be a PEM file."})
            try:
                return upload.read().decode("utf-8")
            except UnicodeDecodeError:
                raise forms.ValidationError({upload_name: "Upload a PEM text file, not a binary one."})
        return self.cleaned_data.get(text_name) or ""

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        cleaned["certificate_pem"] = self._read("certificate_file", "certificate_text")
        cleaned["private_key_pem"] = self._read("private_key_file", "private_key_text")
        if not cleaned["certificate_pem"].strip():
            raise forms.ValidationError({"certificate_file": "Provide the device certificate."})
        return cleaned
