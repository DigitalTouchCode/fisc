from django.contrib import admin

from fiscguy.models import (
    AuditLog,
    Certs,
    Configuration,
    Device,
    FiscalCounter,
    FiscalDay,
    Receipt,
    Taxes,
)


@admin.register(Certs)
class CertsAdmin(admin.ModelAdmin):
    list_display = ("device", "production", "created_at", "updated_at")
    readonly_fields = ("device", "production", "created_at", "updated_at", "csr_preview")
    exclude = ("certificate", "certificate_key", "csr")

    @staticmethod
    def csr_preview(obj):
        if not obj or not obj.csr:
            return ""
        return f"{obj.csr[:64]}..."


admin.site.register(Configuration)
admin.site.register(Taxes)
@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("device_id", "org_name", "production", "created_at")
    exclude = ("activation_key",)
admin.site.register(FiscalDay)
admin.site.register(Receipt)
admin.site.register(FiscalCounter)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_name", "action", "device_ref", "ip_address")
    list_filter = ("action",)
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
