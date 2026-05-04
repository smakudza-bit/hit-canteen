from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('canteen', '0005_notificationlog'),
    ]

    operations = [
        migrations.AddField(
            model_name='meal',
            name='stock_quantity',
            field=models.IntegerField(default=50),
        ),
    ]
