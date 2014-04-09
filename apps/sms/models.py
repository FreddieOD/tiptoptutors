from django.db import models


class SMS(models.Model):
    mobile_number = models.CharField(max_length=12)
    delivery_status = models.CharField(max_length=16, default='unknown')
    created = models.DateTimeField(auto_now_add=True)
