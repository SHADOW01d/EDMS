from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        MANAGER = "MANAGER", "Manager"
        FACTORY = "FACTORY", "Factory"
        BRANCH_MWANZA = "BRANCH_MWANZA", "Mwanza"
        BRANCH_DAR = "BRANCH_DAR", "Dar"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        blank=True,
    )

    def __str__(self):
        return self.get_full_name() or self.username
