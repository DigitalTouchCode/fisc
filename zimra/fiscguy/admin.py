from django.contrib import admin

from fiscguy.models import (Certs, Configuration, Device, FiscalDay, Receipt,
                            Taxes)

admin.site.register(Certs)
admin.site.register(Configuration)
admin.site.register(Taxes)
admin.site.register(Device)
admin.site.register(FiscalDay)
admin.site.register(Receipt)
