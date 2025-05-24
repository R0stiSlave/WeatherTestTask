from django.db import models

class SearchHistory(models.Model):
    city = models.CharField(max_length=100)
    searched_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField()

    def __str__(self):
        return f"{self.city} ({self.searched_at})"