from rest_framework.pagination import CursorPagination


class StandardCursorPagination(CursorPagination):
    """Cursor pagination: stable under concurrent inserts (transaction feeds)."""

    page_size = 20
    max_page_size = 100
    page_size_query_param = "page_size"
    ordering = "-created_at"
