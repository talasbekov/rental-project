from datetime import date

from rest_framework import viewsets, filters as drf_filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Property, PropertyCalendarManager
from .serializers import PropertySerializer
from .filters import PropertyFilter # Import the custom filter
from rest_framework.permissions import IsAuthenticatedOrReadOnly # Allow public read
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

class PropertyViewSet(viewsets.ModelViewSet):
    queryset = Property.objects.all()
    serializer_class = PropertySerializer
    permission_classes = [IsAuthenticatedOrReadOnly] # Allow anyone to view, but only auth users to change
    filter_backends = [DjangoFilterBackend, drf_filters.SearchFilter, drf_filters.OrderingFilter]
    filterset_class = PropertyFilter
    search_fields = ['name', 'address', 'description']
    ordering_fields = ['price_per_day', 'created_at', 'area', 'number_of_rooms']
    ordering = ['-created_at']

    @action(detail=True, methods=['get'])
    def calendar(self, request, pk=None):
        """Получение календаря занятости квартиры"""
        property_obj = self.get_object()

        year = int(request.query_params.get('year', date.today().year))
        month = int(request.query_params.get('month', date.today().month))

        calendar_matrix = PropertyCalendarManager.get_calendar_view(
            property_obj, year, month
        )

        occupancy_rate = PropertyCalendarManager.get_occupancy_rate(
            property_obj,
            date(year, month, 1),
            date(year, month + 1, 1) if month < 12 else date(year + 1, 1, 1)
        )

        return Response({
            'property': property_obj.id,
            'year': year,
            'month': month,
            'calendar': calendar_matrix,
            'occupancy_rate': round(occupancy_rate, 2)
        })

    @action(detail=True, methods=['post'])
    def block_dates(self, request, pk=None):
        """Блокировка дат владельцем"""
        property_obj = self.get_object()

        # Проверка прав (только владелец или админ)
        if property_obj.owner != request.user and not request.user.is_staff:
            return Response(
                {'error': 'Недостаточно прав'},
                status=status.HTTP_403_FORBIDDEN
            )

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        reason = request.data.get('reason', 'Заблокировано владельцем')

        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)

            if end <= start:
                raise ValueError("Дата окончания должна быть после даты начала")

            blocked_days = PropertyCalendarManager.block_dates(
                property_obj, start, end, status='blocked'
            )

            # Сохраняем причину блокировки
            for day in blocked_days:
                day.notes = reason
                day.save()

            return Response({
                'message': f'Заблокировано {len(blocked_days)} дней',
                'blocked_dates': [day.date.isoformat() for day in blocked_days]
            })

        except (ValueError, TypeError) as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
