from django.contrib import admin
from models import Pupil, PupilTutorMatch, PupilPin


class PupilTutorMatchAdmin(admin.StackedInline):
    model = PupilTutorMatch


class PupilAdmin(admin.ModelAdmin):
    search_fields = ["name", 'surname', 'email', ]
    list_display = ("name", 'guardian_name', 'surname', 'email', 'contact_number', 'created_at')
    inlines = [PupilTutorMatchAdmin]


admin.site.register(Pupil, PupilAdmin)
admin.site.register(PupilTutorMatch)
admin.site.register(PupilPin)
