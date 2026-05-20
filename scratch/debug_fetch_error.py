import os
import django
import sys

# Setup Django environment
sys.path.append('c:\\Users\\Tolgacan Kaya\\OneDrive\\Masaüstü\\SaasProject')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.test import RequestFactory
from appointments.views import get_available_times
from businesses.models import Business, Service, Staff

# Get some business and service to test
business = Business.objects.filter(slug='seda-guzellik-ve-bakm-salonu').first()
if not business:
    print("Business not found")
    sys.exit(1)

service = business.services.first()
staff = business.staff_members.first()

print(f"Testing with Business: {business.slug}, Service: {service.id if service else 'None'}, Staff: {staff.id if staff else 'None'}")

factory = RequestFactory()

# We will test May 19, 2026
url = f"/randevu-yonetimi/api/available-times/{business.slug}/?date=2026-05-19&service_id={service.id if service else ''}&staff_id={staff.id if staff else ''}"
request = factory.get(url)

try:
    response = get_available_times(request, business.slug)
    print("STATUS CODE:", response.status_code)
    print("CONTENT:", response.content.decode('utf-8'))
except Exception as e:
    import traceback
    print("EXCEPTION OCCURRED:")
    traceback.print_exc()
