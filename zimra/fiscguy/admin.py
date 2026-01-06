from django.contrib import admin

from fiscguy.models import Certs, Configuration, Device, FiscalDay, Taxes, Receipt

admin.site.register(Certs)
admin.site.register(Configuration)
admin.site.register(Taxes)
admin.site.register(Device)
admin.site.register(FiscalDay)
admin.site.register(Receipt)
