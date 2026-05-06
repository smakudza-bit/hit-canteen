from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/v1/', include('canteen.urls')),
    path('', TemplateView.as_view(template_name='index.html')),

    path('login/', TemplateView.as_view(template_name='student-login.html')),
    path('student-login/', TemplateView.as_view(template_name='student-login.html')),
    path('student-forgot-password/', TemplateView.as_view(template_name='student-forgot-password.html')),
    path('register/', TemplateView.as_view(template_name='register.html')),
    path('email-verification/', TemplateView.as_view(template_name='email-verification.html')),
    path('student/', TemplateView.as_view(template_name='student.html')),
    path('student-add-money/', TemplateView.as_view(template_name='student-add-money.html')),
    path('student-processing/', TemplateView.as_view(template_name='student-processing.html')),
    path('student-payment-success/', TemplateView.as_view(template_name='student-payment-success.html')),
    path('student-scan-pay/', TemplateView.as_view(template_name='student-scan-pay.html')),
    path('student-qr/', TemplateView.as_view(template_name='student-qr.html')),
    path('student-menu/', TemplateView.as_view(template_name='student-menu.html')),
    path('student-cart/', TemplateView.as_view(template_name='student-cart.html')),
    path('student-transactions/', TemplateView.as_view(template_name='student-transactions.html')),
    path('student-profile/', TemplateView.as_view(template_name='student-profile.html')),

    path('staff-login/', TemplateView.as_view(template_name='staff-login.html')),
    path('staff/', TemplateView.as_view(template_name='staff.html')),
    path('staff-scanner/', TemplateView.as_view(template_name='staff-scanner.html')),
    path('staff-verify/', TemplateView.as_view(template_name='staff-verify.html')),
    path('staff-payment-success/', TemplateView.as_view(template_name='staff-payment-success.html')),
    path('staff-transactions/', TemplateView.as_view(template_name='staff-transactions.html')),
    path('staff-summary/', TemplateView.as_view(template_name='staff-summary.html')),

    path('admin-login/', TemplateView.as_view(template_name='admin-login.html')),
    path('admin/', TemplateView.as_view(template_name='admin.html')),
    path('admin-students/', TemplateView.as_view(template_name='admin-students.html')),
    path('admin-staff/', TemplateView.as_view(template_name='admin-staff.html')),
    path('admin-food/', TemplateView.as_view(template_name='admin-food.html')),
    path('admin-transactions/', TemplateView.as_view(template_name='admin-transactions.html')),
    path('admin-reports/', TemplateView.as_view(template_name='admin-reports.html')),
    path('admin-settings/', TemplateView.as_view(template_name='admin-settings.html')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
