from attrs import fields


class AttrsAllowAliasKeyword:
    def __init__(self, *args, **kwargs):
        if kwargs:
            old_kwargs = kwargs
            kwargs = {}
            cls_fields = {a.name: a.alias for a in fields(self.__class__) if a.alias}

            for key, val in old_kwargs.items():
                kwargs[cls_fields.get(key, key)] = val

        self.__attrs_init__(*args, **kwargs)
