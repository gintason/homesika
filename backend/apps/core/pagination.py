from rest_framework.pagination import CursorPagination


class StandardCursorPagination(CursorPagination):
    """Cursor pagination: stable under concurrent inserts (transaction feeds). A view can set
    `cursor_ordering` (a tuple of fields) to page in its own order; cursor pagination ignores order_by()."""

    page_size = 20
    max_page_size = 100
    page_size_query_param = "page_size"
    ordering = "-created_at"

    def get_ordering(self, request, queryset, view):
        return getattr(view, "cursor_ordering", None) or super().get_ordering(request, queryset, view)
