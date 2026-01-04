from django.contrib import admin

from fiscguy.models import (
    Certs, 
    Configuration, 
    Taxes, 
    Device,
    FiscalDay
)

admin.site.register(Certs)
admin.site.register(Configuration)
admin.site.register(Taxes)
admin.site.register(Device)
admin.site.register(FiscalDay)
