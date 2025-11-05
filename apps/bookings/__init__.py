"""Bookings app package.

This app encapsulates the booking domain, including the booking model
and related services such as availability checks, hold expirations and
payment integration. Bookings ensure atomicity and enforce date
overlap constraints via database transactions and the use of exclusion
indexes when supported.
"""
