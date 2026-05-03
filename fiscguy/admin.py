from django.contrib import admin

from fiscguy.models import (
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
admin.site.register(Device)
admin.site.register(FiscalDay)
admin.site.register(Receipt)
admin.site.register(FiscalCounter)
