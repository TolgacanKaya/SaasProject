from django.contrib import admin
from .models import Category, Business, Service, Customer

admin.site.register(Category)
admin.site.register(Business)
admin.site.register(Service)
admin.site.register(Customer)