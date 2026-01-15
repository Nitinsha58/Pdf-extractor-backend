# Create your views here.
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from django.core.files.storage import default_storage
from django.db.models import Max
from django.db import IntegrityError
from .models import (
    Chapter,
    ClassName,
    Concept,
    CroppedImage,
    CroppedImageExtra,
    ImageType,
    QuestionType,
    Sources,
    Subject,
    Topic,
    UsageType,
)
from .serializers import (
    ChapterSerializer,
    ChapterWriteSerializer,
    ClassNameSerializer,
    ClassNameWriteSerializer,
    ConceptSerializer,
    ConceptWriteSerializer,
    CropSerializer,
    CroppedImageReadSerializer,
    CroppedImageWriteSerializer,
    ImageTypeSerializer,
    QuestionTypeSerializer,
    SourcesSerializer,
    SubjectSerializer,
    SubjectWriteSerializer,
    TopicSerializer,
    TopicWriteSerializer,
    UsageTypeSerializer,
)
import json


class UploadCrop(APIView):
    # ensure multipart/form-data (files + fields) is parsed correctly
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        # Build a plain dict payload (not a QueryDict) so we can store
        # non-string values (like parsed JSON) without coercion.
        payload = {}

        # Copy scalar/form fields and attempt to parse JSON-encoded fields
        for k, v in request.data.items():
            # log types for easier debugging
            print(f"Received field {k}: type={type(v).__name__} repr={repr(v)[:200]}")

            if k in ("rectPdf", "rectScreen", "rect_pdf", "rect_screen") and isinstance(v, str):
                try:
                    payload[k] = json.loads(v)
                    continue
                except json.JSONDecodeError:
                    # fallthrough and store original string so serializer reports error
                    pass

            payload[k] = v

        # Include uploaded file (if present) from request.FILES
        if "image" in request.FILES:
            payload["image"] = request.FILES.get("image")

        # ---- Field name normalization (frontend camelCase -> backend snake_case) ----
        rename_map = {
            "rectPdf": "rect_pdf",
            "rectScreen": "rect_screen",
            "usage": "usage_type",
            "questionType": "question_type",
            "imageType": "image_type",
            "classId": "class_name",
            "subjectId": "subject",
            "chapterId": "chapter",
            "conceptId": "concept",
            "topicId": "topic",
        }
        for src, dst in rename_map.items():
            if src in payload and dst not in payload:
                payload[dst] = payload.pop(src)

        # No longer stored on CroppedImage; drop if frontend still sends them
        payload.pop("pageNo", None)
        payload.pop("documentName", None)
        payload.pop("page_no", None)
        payload.pop("document_name", None)

        # ---- Resolve / create related objects by ID or name ----
        def _as_int(val):
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        def _get_by_id_or_name(model, value, name_field="name"):
            if value is None:
                return None
            pk = _as_int(value)
            if pk is not None:
                return model.objects.get(pk=pk)
            obj, _ = model.objects.get_or_create(**{name_field: str(value)})
            return obj

        # Taxonomy resolution (creates rows if you send strings)
        class_obj = _get_by_id_or_name(ClassName, payload.get("class_name"))
        subject_obj = _get_by_id_or_name(Subject, payload.get("subject"))

        chapter_val = payload.get("chapter")
        chapter_obj = None
        if chapter_val is not None and class_obj is not None and subject_obj is not None:
            pk = _as_int(chapter_val)
            if pk is not None:
                chapter_obj = Chapter.objects.get(pk=pk)
            else:
                chapter_obj, _ = Chapter.objects.get_or_create(
                    name=str(chapter_val),
                    class_name=class_obj,
                    subject=subject_obj,
                )

        concept_val = payload.get("concept")
        concept_obj = None
        if concept_val is not None and chapter_obj is not None:
            pk = _as_int(concept_val)
            if pk is not None:
                concept_obj = Concept.objects.get(pk=pk)
            else:
                concept_obj, _ = Concept.objects.get_or_create(
                    name=str(concept_val),
                    chapter=chapter_obj,
                )

        topic_val = payload.get("topic")
        topic_obj = None
        if topic_val is not None and concept_obj is not None:
            pk = _as_int(topic_val)
            if pk is not None:
                topic_obj = Topic.objects.get(pk=pk)
            else:
                topic_obj, _ = Topic.objects.get_or_create(
                    name=str(topic_val),
                    concept=concept_obj,
                )

        question_type_obj = _get_by_id_or_name(QuestionType, payload.get("question_type"))
        image_type_obj = _get_by_id_or_name(ImageType, payload.get("image_type"))
        source_obj = _get_by_id_or_name(Sources, payload.get("source"))

        # Write resolved objects back to payload for serializer
        if class_obj is not None:
            payload["class_name"] = class_obj.pk
        if subject_obj is not None:
            payload["subject"] = subject_obj.pk
        if chapter_obj is not None:
            payload["chapter"] = chapter_obj.pk
        if concept_obj is not None:
            payload["concept"] = concept_obj.pk
        if topic_obj is not None:
            payload["topic"] = topic_obj.pk
        if question_type_obj is not None:
            payload["question_type"] = question_type_obj.pk
        if image_type_obj is not None:
            payload["image_type"] = image_type_obj.pk
        if source_obj is not None:
            payload["source"] = source_obj.pk

        # Usage: accept a single usage type name/id and attach it after save
        usage_value = payload.pop("usage_type", None)

        serializer = CropSerializer(data=payload)

        if serializer.is_valid():
            cropped = serializer.save()
            if usage_value is not None:
                usage_obj = _get_by_id_or_name(UsageType, usage_value)
                if usage_obj is not None:
                    cropped.usage_types.add(usage_obj)
            return Response(CropSerializer(cropped).data, status=201)

        print("❌ Serializer errors:", serializer.errors)
        return Response(serializer.errors, status=400)


class UploadCropBulk(APIView):
    """All-or-nothing bulk upload.

    Expects multipart/form-data with:
    - items: JSON array of metadata objects (one per image)
    - image_0, image_1, ...: corresponding files

    If any item fails validation or save, nothing is persisted.
    """

    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        items_raw = request.data.get("items")
        if not items_raw:
            return Response(
                {"items": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            items = json.loads(items_raw) if isinstance(items_raw, str) else items_raw
        except json.JSONDecodeError:
            return Response(
                {"items": ["Invalid JSON."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not isinstance(items, list):
            return Response(
                {"items": ["Must be a JSON array."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        rename_map = {
            "rectPdf": "rect_pdf",
            "rectScreen": "rect_screen",
            "usage": "usage_type",
            "questionType": "question_type",
            "imageType": "image_type",
            "classId": "class_name",
            "subjectId": "subject",
            "chapterId": "chapter",
            "conceptId": "concept",
            "topicId": "topic",
        }

        def _as_int(val):
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        def _get_by_id_or_name(model, value, name_field="name"):
            if value is None:
                return None
            pk = _as_int(value)
            if pk is not None:
                return model.objects.get(pk=pk)
            obj, _ = model.objects.get_or_create(**{name_field: str(value)})
            return obj

        created = []
        created_extras = []
        created_file_names = []
        primary_by_group_key = {}

        try:
            with transaction.atomic():
                for idx, item in enumerate(items):
                    if not isinstance(item, dict):
                        raise ValidationError({"items": {idx: "Each item must be an object."}})

                    payload = dict(item)

                    group_key = (
                        payload.get("groupKey")
                        or payload.get("group_key")
                        or payload.get("questionGroup")
                        or payload.get("question_group")
                    )
                    if group_key is None:
                        group_key = f"__single__{idx}"

                    # Attach file
                    file_key = f"image_{idx}"
                    upload_file = request.FILES.get(file_key)
                    if not upload_file:
                        raise ValidationError({"items": {idx: {file_key: "Missing file."}}})
                    payload["image"] = upload_file

                    # Parse JSON fields if needed
                    for k in ("rectPdf", "rectScreen", "rect_pdf", "rect_screen"):
                        if k in payload and isinstance(payload[k], str):
                            try:
                                payload[k] = json.loads(payload[k])
                            except json.JSONDecodeError:
                                pass

                    # Normalize keys
                    for src, dst in rename_map.items():
                        if src in payload and dst not in payload:
                            payload[dst] = payload.pop(src)

                    # Drop removed fields if frontend still sends them
                    payload.pop("pageNo", None)
                    payload.pop("documentName", None)
                    payload.pop("page_no", None)
                    payload.pop("document_name", None)

                    group_index_raw = payload.get("groupIndex") or payload.get("group_index")
                    group_index = _as_int(group_index_raw)

                    # If this group already has a primary CroppedImage, store this as an extra image.
                    primary = primary_by_group_key.get(str(group_key))
                    if primary is not None:
                        # Extra images inherit question metadata from primary.
                        extra_image_type_obj = None
                        if payload.get("image_type") not in (None, ""):
                            extra_image_type_obj = _get_by_id_or_name(ImageType, payload.get("image_type"))

                        # Determine stable order within the group.
                        # If frontend provides groupIndex (1=primary, 2..n=extras) we store it.
                        # Otherwise we append after the last known extra.
                        if group_index is None or group_index < 2:
                            last = primary.extra_images.aggregate(m=Max("sort_order")).get("m")
                            group_index = (last or 1) + 1

                        extra = CroppedImageExtra.objects.create(
                            parent=primary,
                            image=payload["image"],
                            image_type=extra_image_type_obj or primary.image_type,
                            rect_pdf=payload.get("rect_pdf") or {},
                            rect_screen=payload.get("rect_screen") or {},
                            sort_order=group_index,
                        )
                        created_extras.append(extra)
                        if getattr(extra.image, "name", None):
                            created_file_names.append(extra.image.name)
                        continue

                    # Resolve taxonomy
                    class_obj = _get_by_id_or_name(ClassName, payload.get("class_name"))
                    subject_obj = _get_by_id_or_name(Subject, payload.get("subject"))

                    chapter_val = payload.get("chapter")
                    chapter_obj = None
                    if chapter_val is not None and class_obj is not None and subject_obj is not None:
                        pk = _as_int(chapter_val)
                        if pk is not None:
                            chapter_obj = Chapter.objects.get(pk=pk)
                        else:
                            chapter_obj, _ = Chapter.objects.get_or_create(
                                name=str(chapter_val),
                                class_name=class_obj,
                                subject=subject_obj,
                            )

                    concept_val = payload.get("concept")
                    concept_obj = None
                    if concept_val is not None and chapter_obj is not None:
                        pk = _as_int(concept_val)
                        if pk is not None:
                            concept_obj = Concept.objects.get(pk=pk)
                        else:
                            concept_obj, _ = Concept.objects.get_or_create(
                                name=str(concept_val),
                                chapter=chapter_obj,
                            )

                    topic_val = payload.get("topic")
                    topic_obj = None
                    if topic_val is not None and concept_obj is not None:
                        pk = _as_int(topic_val)
                        if pk is not None:
                            topic_obj = Topic.objects.get(pk=pk)
                        else:
                            topic_obj, _ = Topic.objects.get_or_create(
                                name=str(topic_val),
                                concept=concept_obj,
                            )

                    question_type_obj = _get_by_id_or_name(QuestionType, payload.get("question_type"))
                    image_type_obj = _get_by_id_or_name(ImageType, payload.get("image_type"))
                    source_obj = _get_by_id_or_name(Sources, payload.get("source"))

                    if class_obj is not None:
                        payload["class_name"] = class_obj.pk
                    if subject_obj is not None:
                        payload["subject"] = subject_obj.pk
                    if chapter_obj is not None:
                        payload["chapter"] = chapter_obj.pk
                    if concept_obj is not None:
                        payload["concept"] = concept_obj.pk
                    if topic_obj is not None:
                        payload["topic"] = topic_obj.pk
                    if question_type_obj is not None:
                        payload["question_type"] = question_type_obj.pk
                    if image_type_obj is not None:
                        payload["image_type"] = image_type_obj.pk
                    if source_obj is not None:
                        payload["source"] = source_obj.pk

                    usage_value = payload.pop("usage_type", None)

                    # Not a model field on CroppedImage; used only for grouping.
                    payload.pop("groupIndex", None)
                    payload.pop("group_index", None)

                    serializer = CropSerializer(data=payload)
                    serializer.is_valid(raise_exception=True)
                    cropped = serializer.save()
                    created.append(cropped)
                    if getattr(cropped.image, "name", None):
                        created_file_names.append(cropped.image.name)

                    primary_by_group_key[str(group_key)] = cropped

                    if usage_value is not None:
                        usage_obj = _get_by_id_or_name(UsageType, usage_value)
                        if usage_obj is not None:
                            cropped.usage_types.add(usage_obj)

            # Backward-compatible response: still returns created primary crops.
            # Extras are linked and can be fetched via CroppedImageReadSerializer.
            return Response(CropSerializer(created, many=True).data, status=201)

        except ValidationError as e:
            # Ensure no orphan files remain if storage wrote files before DB rollback
            for name in created_file_names:
                try:
                    default_storage.delete(name)
                except Exception:
                    pass
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            for name in created_file_names:
                try:
                    default_storage.delete(name)
                except Exception:
                    pass
            return Response(
                {"detail": "Upload failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ClassList(APIView):
    def get(self, request):
        qs = ClassName.objects.all().order_by("name")
        return Response(ClassNameSerializer(qs, many=True).data)

    def post(self, request):
        serializer = ClassNameWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response({"name": ["Class with this name already exists."]}, status=400)
        return Response(ClassNameSerializer(obj).data, status=201)


class ClassDetail(APIView):
    def patch(self, request, pk):
        obj = ClassName.objects.get(pk=pk)
        serializer = ClassNameWriteSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response({"name": ["Class with this name already exists."]}, status=400)
        return Response(ClassNameSerializer(obj).data)

    def delete(self, request, pk):
        ClassName.objects.filter(pk=pk).delete()
        return Response(status=204)


class ClassBulk(APIView):
    """Bulk create/update/delete in one request.

    Payload:
      {
        "create": [{"name": "..."}],
        "update": [{"id": 1, "name": "..."}],
        "delete": [1,2,3]
      }
    """

    def post(self, request):
        create_items = request.data.get("create") or []
        update_items = request.data.get("update") or []
        delete_items = request.data.get("delete") or []

        if not isinstance(create_items, list) or not isinstance(update_items, list) or not isinstance(delete_items, list):
            raise ValidationError({"detail": "create/update/delete must be arrays."})

        created = []
        updated = []

        with transaction.atomic():
            # deletes
            if delete_items:
                ClassName.objects.filter(pk__in=delete_items).delete()

            # creates
            for item in create_items:
                s = ClassNameWriteSerializer(data=item)
                s.is_valid(raise_exception=True)
                try:
                    created.append(s.save())
                except IntegrityError:
                    raise ValidationError({"create": ["Duplicate name."]})

            # updates
            for item in update_items:
                pk = item.get("id")
                if not pk:
                    raise ValidationError({"update": ["Each update item must include id."]})
                obj = ClassName.objects.get(pk=pk)
                s = ClassNameWriteSerializer(obj, data=item, partial=True)
                s.is_valid(raise_exception=True)
                try:
                    updated.append(s.save())
                except IntegrityError:
                    raise ValidationError({"update": [f"Duplicate name for id={pk}."]})

        return Response(
            {
                "created": ClassNameSerializer(created, many=True).data,
                "updated": ClassNameSerializer(updated, many=True).data,
                "deleted": delete_items,
            },
            status=200,
        )


class SubjectList(APIView):
    def get(self, request):
        qs = Subject.objects.all().order_by("name")
        return Response(SubjectSerializer(qs, many=True).data)

    def post(self, request):
        serializer = SubjectWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response({"name": ["Subject with this name already exists."]}, status=400)
        return Response(SubjectSerializer(obj).data, status=201)


class SubjectDetail(APIView):
    def patch(self, request, pk):
        obj = Subject.objects.get(pk=pk)
        serializer = SubjectWriteSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response({"name": ["Subject with this name already exists."]}, status=400)
        return Response(SubjectSerializer(obj).data)

    def delete(self, request, pk):
        Subject.objects.filter(pk=pk).delete()
        return Response(status=204)


class SubjectBulk(APIView):
    def post(self, request):
        create_items = request.data.get("create") or []
        update_items = request.data.get("update") or []
        delete_items = request.data.get("delete") or []

        if not isinstance(create_items, list) or not isinstance(update_items, list) or not isinstance(delete_items, list):
            raise ValidationError({"detail": "create/update/delete must be arrays."})

        created = []
        updated = []
        with transaction.atomic():
            if delete_items:
                Subject.objects.filter(pk__in=delete_items).delete()
            for item in create_items:
                s = SubjectWriteSerializer(data=item)
                s.is_valid(raise_exception=True)
                try:
                    created.append(s.save())
                except IntegrityError:
                    raise ValidationError({"create": ["Duplicate name."]})
            for item in update_items:
                pk = item.get("id")
                if not pk:
                    raise ValidationError({"update": ["Each update item must include id."]})
                obj = Subject.objects.get(pk=pk)
                s = SubjectWriteSerializer(obj, data=item, partial=True)
                s.is_valid(raise_exception=True)
                try:
                    updated.append(s.save())
                except IntegrityError:
                    raise ValidationError({"update": [f"Duplicate name for id={pk}."]})

        return Response(
            {
                "created": SubjectSerializer(created, many=True).data,
                "updated": SubjectSerializer(updated, many=True).data,
                "deleted": delete_items,
            },
            status=200,
        )


class ChapterList(APIView):
    def get(self, request):
        qs = Chapter.objects.select_related("class_name", "subject").all()

        def _as_int(val):
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        class_val = (
            request.query_params.get("class_id")
            or request.query_params.get("classId")
            or request.query_params.get("class")
        )
        subject_val = (
            request.query_params.get("subject_id")
            or request.query_params.get("subjectId")
            or request.query_params.get("subject")
        )

        if class_val is not None:
            class_pk = _as_int(class_val)
            if class_pk is not None:
                qs = qs.filter(class_name_id=class_pk)
            else:
                qs = qs.filter(class_name__name=class_val)

        if subject_val is not None:
            subject_pk = _as_int(subject_val)
            if subject_pk is not None:
                qs = qs.filter(subject_id=subject_pk)
            else:
                qs = qs.filter(subject__name=subject_val)

        qs = qs.order_by("name")
        return Response(ChapterSerializer(qs, many=True).data)

    def post(self, request):
        serializer = ChapterWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response({"name": ["Chapter already exists for this class+subject." ]}, status=400)
        return Response(ChapterSerializer(obj).data, status=201)


class ChapterDetail(APIView):
    def patch(self, request, pk):
        obj = Chapter.objects.get(pk=pk)
        serializer = ChapterWriteSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response({"name": ["Chapter already exists for this class+subject."]}, status=400)
        return Response(ChapterSerializer(obj).data)

    def delete(self, request, pk):
        Chapter.objects.filter(pk=pk).delete()
        return Response(status=204)


class ChapterBulk(APIView):
    def post(self, request):
        create_items = request.data.get("create") or []
        update_items = request.data.get("update") or []
        delete_items = request.data.get("delete") or []

        if not isinstance(create_items, list) or not isinstance(update_items, list) or not isinstance(delete_items, list):
            raise ValidationError({"detail": "create/update/delete must be arrays."})

        created = []
        updated = []
        with transaction.atomic():
            if delete_items:
                Chapter.objects.filter(pk__in=delete_items).delete()

            for item in create_items:
                s = ChapterWriteSerializer(data=item)
                s.is_valid(raise_exception=True)
                try:
                    created.append(s.save())
                except IntegrityError:
                    raise ValidationError({"create": ["Duplicate chapter for class+subject."]})

            for item in update_items:
                pk = item.get("id")
                if not pk:
                    raise ValidationError({"update": ["Each update item must include id."]})
                obj = Chapter.objects.get(pk=pk)
                s = ChapterWriteSerializer(obj, data=item, partial=True)
                s.is_valid(raise_exception=True)
                try:
                    updated.append(s.save())
                except IntegrityError:
                    raise ValidationError({"update": [f"Duplicate chapter for id={pk}."]})

        return Response(
            {
                "created": ChapterSerializer(created, many=True).data,
                "updated": ChapterSerializer(updated, many=True).data,
                "deleted": delete_items,
            },
            status=200,
        )


class ConceptList(APIView):
    def get(self, request):
        qs = Concept.objects.select_related(
            "chapter",
            "chapter__class_name",
            "chapter__subject",
        ).all()

        def _as_int(val):
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        class_val = (
            request.query_params.get("class_id")
            or request.query_params.get("classId")
            or request.query_params.get("class")
        )
        subject_val = (
            request.query_params.get("subject_id")
            or request.query_params.get("subjectId")
            or request.query_params.get("subject")
        )
        chapter_val = (
            request.query_params.get("chapter_id")
            or request.query_params.get("chapterId")
            or request.query_params.get("chapter")
        )

        if class_val is not None:
            class_pk = _as_int(class_val)
            if class_pk is not None:
                qs = qs.filter(chapter__class_name_id=class_pk)
            else:
                qs = qs.filter(chapter__class_name__name=class_val)

        if subject_val is not None:
            subject_pk = _as_int(subject_val)
            if subject_pk is not None:
                qs = qs.filter(chapter__subject_id=subject_pk)
            else:
                qs = qs.filter(chapter__subject__name=subject_val)

        if chapter_val is not None:
            chapter_pk = _as_int(chapter_val)
            if chapter_pk is not None:
                qs = qs.filter(chapter_id=chapter_pk)
            else:
                qs = qs.filter(chapter__name=chapter_val)

        qs = qs.order_by("name")
        return Response(ConceptSerializer(qs, many=True).data)

    def post(self, request):
        serializer = ConceptWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response(
                {"name": ["Concept already exists for this chapter."]},
                status=400,
            )
        return Response(ConceptSerializer(obj).data, status=201)


class ConceptDetail(APIView):
    def patch(self, request, pk):
        obj = Concept.objects.get(pk=pk)
        serializer = ConceptWriteSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response(
                {"name": ["Concept already exists for this chapter."]},
                status=400,
            )
        return Response(ConceptSerializer(obj).data)

    def delete(self, request, pk):
        Concept.objects.filter(pk=pk).delete()
        return Response(status=204)


class ConceptBulk(APIView):
    def post(self, request):
        create_items = request.data.get("create") or []
        update_items = request.data.get("update") or []
        delete_items = request.data.get("delete") or []

        if not isinstance(create_items, list) or not isinstance(update_items, list) or not isinstance(delete_items, list):
            raise ValidationError({"detail": "create/update/delete must be arrays."})

        created = []
        updated = []
        created_id_map = []
        with transaction.atomic():
            if delete_items:
                Concept.objects.filter(pk__in=delete_items).delete()

            for item in create_items:
                if not isinstance(item, dict):
                    raise ValidationError({"create": ["Each create item must be an object."]})

                payload = dict(item)
                client_id = payload.pop("client_id", None)
                if client_id is None:
                    client_id = payload.pop("clientId", None)

                s = ConceptWriteSerializer(data=payload)
                s.is_valid(raise_exception=True)
                try:
                    obj = s.save()
                    created.append(obj)
                    if client_id is not None:
                        created_id_map.append({"client_id": client_id, "id": obj.pk})
                except IntegrityError:
                    raise ValidationError({"create": ["Duplicate concept for chapter."]})

            for item in update_items:
                pk = item.get("id")
                if not pk:
                    raise ValidationError({"update": ["Each update item must include id."]})
                obj = Concept.objects.get(pk=pk)
                s = ConceptWriteSerializer(obj, data=item, partial=True)
                s.is_valid(raise_exception=True)
                try:
                    updated.append(s.save())
                except IntegrityError:
                    raise ValidationError({"update": [f"Duplicate concept for id={pk}."]})

        return Response(
            {
                "created": ConceptSerializer(created, many=True).data,
                "updated": ConceptSerializer(updated, many=True).data,
                "deleted": delete_items,
                "created_id_map": created_id_map,
            },
            status=200,
        )


class TopicList(APIView):
    def get(self, request):
        qs = Topic.objects.select_related(
            "concept",
            "concept__chapter",
            "concept__chapter__class_name",
            "concept__chapter__subject",
        ).all()

        def _as_int(val):
            try:
                return int(val)
            except (TypeError, ValueError):
                return None

        class_val = (
            request.query_params.get("class_id")
            or request.query_params.get("classId")
            or request.query_params.get("class")
        )
        subject_val = (
            request.query_params.get("subject_id")
            or request.query_params.get("subjectId")
            or request.query_params.get("subject")
        )
        chapter_val = (
            request.query_params.get("chapter_id")
            or request.query_params.get("chapterId")
            or request.query_params.get("chapter")
        )
        concept_val = (
            request.query_params.get("concept_id")
            or request.query_params.get("conceptId")
            or request.query_params.get("concept")
        )

        if class_val is not None:
            class_pk = _as_int(class_val)
            if class_pk is not None:
                qs = qs.filter(concept__chapter__class_name_id=class_pk)
            else:
                qs = qs.filter(concept__chapter__class_name__name=class_val)

        if subject_val is not None:
            subject_pk = _as_int(subject_val)
            if subject_pk is not None:
                qs = qs.filter(concept__chapter__subject_id=subject_pk)
            else:
                qs = qs.filter(concept__chapter__subject__name=subject_val)

        if chapter_val is not None:
            chapter_pk = _as_int(chapter_val)
            if chapter_pk is not None:
                qs = qs.filter(concept__chapter_id=chapter_pk)
            else:
                qs = qs.filter(concept__chapter__name=chapter_val)

        if concept_val is not None:
            concept_pk = _as_int(concept_val)
            if concept_pk is not None:
                qs = qs.filter(concept_id=concept_pk)
            else:
                qs = qs.filter(concept__name=concept_val)

        qs = qs.order_by("concept_id", "name")
        return Response(TopicSerializer(qs, many=True).data)

    def post(self, request):
        serializer = TopicWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response(
                {"name": ["Topic already exists for this concept."]},
                status=400,
            )
        return Response(TopicSerializer(obj).data, status=201)


class TopicDetail(APIView):
    def patch(self, request, pk):
        obj = Topic.objects.get(pk=pk)
        serializer = TopicWriteSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            return Response(
                {"name": ["Topic already exists for this concept."]},
                status=400,
            )
        return Response(TopicSerializer(obj).data)

    def delete(self, request, pk):
        Topic.objects.filter(pk=pk).delete()
        return Response(status=204)


class TopicBulk(APIView):
    def post(self, request):
        create_items = request.data.get("create") or []
        update_items = request.data.get("update") or []
        delete_items = request.data.get("delete") or []

        if not isinstance(create_items, list) or not isinstance(update_items, list) or not isinstance(delete_items, list):
            raise ValidationError({"detail": "create/update/delete must be arrays."})

        created = []
        updated = []
        with transaction.atomic():
            if delete_items:
                Topic.objects.filter(pk__in=delete_items).delete()

            for item in create_items:
                s = TopicWriteSerializer(data=item)
                s.is_valid(raise_exception=True)
                try:
                    created.append(s.save())
                except IntegrityError:
                    raise ValidationError({"create": ["Duplicate topic for concept."]})

            for item in update_items:
                pk = item.get("id")
                if not pk:
                    raise ValidationError({"update": ["Each update item must include id."]})
                obj = Topic.objects.get(pk=pk)
                s = TopicWriteSerializer(obj, data=item, partial=True)
                s.is_valid(raise_exception=True)
                try:
                    updated.append(s.save())
                except IntegrityError:
                    raise ValidationError({"update": [f"Duplicate topic for id={pk}."]})

        return Response(
            {
                "created": TopicSerializer(created, many=True).data,
                "updated": TopicSerializer(updated, many=True).data,
                "deleted": delete_items,
            },
            status=200,
        )


class ImageTypeList(APIView):
    def get(self, request):
        qs = ImageType.objects.all().order_by("created_at")
        return Response(ImageTypeSerializer(qs, many=True).data)


class QuestionTypeList(APIView):
    def get(self, request):
        qs = QuestionType.objects.all().order_by("created_at")
        return Response(QuestionTypeSerializer(qs, many=True).data)


class UsageTypeList(APIView):
    def get(self, request):
        qs = UsageType.objects.all().order_by("created_at")
        return Response(UsageTypeSerializer(qs, many=True).data)


class SourcesList(APIView):
    def get(self, request):
        qs = Sources.objects.all().order_by("created_at")
        return Response(SourcesSerializer(qs, many=True).data)


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class CroppedImageList(APIView):
    def get(self, request):
        qs = CroppedImage.objects.all().order_by("-created_at")

        fk_filters = {
            "image_type": "image_type_id",
            "class_name": "class_name_id",
            "subject": "subject_id",
            "chapter": "chapter_id",
            "concept": "concept_id",
            "topic": "topic_id",
            "question_type": "question_type_id",
            "source": "source_id",
        }
        for query_key, field_name in fk_filters.items():
            value = request.query_params.get(query_key)
            if value in (None, ""):
                continue
            parsed = _as_int(value)
            if parsed is None:
                continue
            qs = qs.filter(**{field_name: parsed})

        difficulty = request.query_params.get("difficulty")
        if difficulty:
            qs = qs.filter(difficulty=difficulty)

        marks = request.query_params.get("marks")
        if marks not in (None, ""):
            parsed_marks = _as_int(marks)
            if parsed_marks is not None:
                qs = qs.filter(marks=parsed_marks)

        priority = request.query_params.get("priority")
        if priority not in (None, ""):
            parsed_priority = _as_int(priority)
            if parsed_priority is not None:
                qs = qs.filter(priority=parsed_priority)

        verified = request.query_params.get("verified")
        if verified in ("0", "1", "true", "false", "True", "False"):
            truthy = verified in ("1", "true", "True")
            qs = qs.filter(verified=truthy)

        is_active = request.query_params.get("is_active")
        if is_active in ("0", "1", "true", "false", "True", "False"):
            truthy = is_active in ("1", "true", "True")
            qs = qs.filter(is_active=truthy)

        usage_types = request.query_params.get("usage_types") or request.query_params.get("usage_type")
        if usage_types:
            parts = [p.strip() for p in str(usage_types).split(",") if p.strip()]
            ids = [i for i in (_as_int(p) for p in parts) if i is not None]
            if ids:
                qs = qs.filter(usage_types__id__in=ids).distinct()

        page = _as_int(request.query_params.get("page") or 1) or 1
        page_size = _as_int(request.query_params.get("page_size") or 50) or 50
        page_size = max(1, min(page_size, 200))
        start = (page - 1) * page_size
        end = start + page_size

        items = list(qs[start:end])
        serializer = CroppedImageReadSerializer(items, many=True, context={"request": request})

        return Response(
            {
                "results": serializer.data,
                "page": page,
                "page_size": page_size,
                "count": qs.count(),
            }
        )


class CroppedImageDetail(APIView):
    def patch(self, request, pk):
        try:
            item = CroppedImage.objects.get(pk=pk)
        except CroppedImage.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = CroppedImageWriteSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = serializer.save()
        return Response(CroppedImageReadSerializer(item, context={"request": request}).data)

    def delete(self, request, pk):
        try:
            item = CroppedImage.objects.get(pk=pk)
        except CroppedImage.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        item.delete()
        return Response(status=204)
