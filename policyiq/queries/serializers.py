from rest_framework import serializers


class CitationSerializer(serializers.Serializer):
    document_name = serializers.CharField()
    page_number = serializers.IntegerField(required=False, allow_null=True)
    similarity_score = serializers.FloatField()
    text_preview = serializers.CharField()


class QueryRequestSerializer(serializers.Serializer):
    question = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)
    document_id = serializers.UUIDField(required=False, allow_null=True)


class QueryResponseSerializer(serializers.Serializer):
    answer = serializers.CharField()
    citations = CitationSerializer(many=True)
