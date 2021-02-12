import datetime
import json
import os
from typing import List, Optional, Union

import black
import jinja2
import typer

# Define a couple of container classes for the Jinja2 template rendering

jinja_environment = jinja2.Environment()

# python's reserved words which cannot be variable names
reserved_words = {"class", "def", "from", "import", "return", "yield"}


class Field:
    def __init__(self, name: str, type_: str, description: Union[str, dict]):
        self.name = f"{name}_" if name in reserved_words else name
        self.alias = name
        self.type = type_
        self.description = (
            description if isinstance(description, str) else description["@value"]
        )

    @property
    def formatted_description(self):
        """An ad-hoc formatted python string, split over many lines. This is
        useful to cope with black's lack of string formatting
        capabilities.

        """
        return "\n        ".join(
            repr(f"{line} ")
            for line in jinja_environment.filters["wordwrap"](
                jinja_environment,
                self.description,
                width=66,
                break_long_words=False,
                break_on_hyphens=False,
                wrapstring="\n",
            ).splitlines()
        )


class Model:
    def __init__(self, name: str, description: Union[str, dict], fields: list[Field]):
        self.name = f"_{name}" if name[0].isdigit() else name
        self.type_marker = name
        self.description = (
            description if isinstance(description, str) else description["@value"]
        )
        self.fields = fields

    def __str__(self):
        return self.name

    @property
    def formatted_description(self):
        """An ad-hoc formatted python string, split over many lines. This is
        useful to cope with black's lack of string formatting
        capabilities.

        """
        return jinja_environment.filters["wordwrap"](
            jinja_environment,
            self.description,
            width=79,
            break_long_words=False,
            break_on_hyphens=False,
            wrapstring="\n    ",
        )


class Enum:
    def __init__(self, name: str, description: Union[str, dict], members: list[str]):
        self.name = name
        self.description = (
            description if isinstance(description, str) else description["@value"]
        )
        self.members = members

    @property
    def formatted_description(self):
        """An ad-hoc formatted python string, split over many lines. This is
        useful to cope with black's lack of string formatting
        capabilities.

        """
        return jinja_environment.filters["wordwrap"](
            jinja_environment,
            self.description,
            width=79,
            break_long_words=False,
            break_on_hyphens=False,
            wrapstring="\n    ",
        )


# A mapping of schema.org DataType(s) to pydantic types
# Reference: https://schema.org/DataType
data_type_map = {
    "Boolean": "StrictBool",
    "False": "Literal[False]",
    "True": "Literal[True]",
    "Date": "date",
    "DateTime": "datetime",
    "Time": "time",
    "Number": "Decimal",
    "Float": "float",
    "Integer": "int",
    "Text": "str",
    "CssSelectorType": "str",
    "PronounceableText": "str",
    "URL": "AnyUrl",
    "XPathType": "str",
}

# A mapping of schema.org DataType(s) to specificity, where a higher
# number is a more specific DataType. This is required because of
# pydantics handling of Union types: [...] it is recommended that,
# when defining Union annotations, the most specific type is included
# first and followed by less specific types [...]
# Source: https://pydantic-docs.helpmanual.io/usage/types/#unions
data_type_specificity = {
    "Boolean": 1,
    "False": 1,
    "True": 1,
    "Date": 4,
    "DateTime": 5,
    "Time": 4,
    "Number": 3,
    "Float": 4,
    "Integer": 5,
    "Text": 1,
    "CssSelectorType": 1,
    "PronounceableText": 1,
    "URL": 2,
    "XPathType": 1,
}


def _setify(thing, prop="@id") -> set[str]:
    """Transforms the thing into a set of its contents, or a singleton
    set, or an empty set, depending on what *thing* is.

    """
    if isinstance(thing, list):
        return set(item[prop] if prop is not None else item for item in thing)
    elif thing is None:
        return set()
    else:
        return set([thing[prop] if prop is not None else thing])


class Registry:
    """A registry of pydantic models linked one-to-one to schema.org
    Type(s), including DataType(s).

    """

    def __init__(
        self,
        vocabulary_file: str,
        type_map: dict[str, str],
        type_specificity: dict[str, int],
        prune_to: Optional[list[str]],
    ):
        self._vocabulary_file = vocabulary_file
        # A mapping of @id to graph node
        self._vocabulary = None
        # A mapping of type name to pydantic type
        self._type_cache = dict(type_map)
        # A mapping of type name to specificity
        self._type_specificity = dict(type_specificity)
        # A mapping of type name to enum type
        self._enums = {}
        # A list of models to limit the generated source
        self._prune_to = prune_to
        # A mapping of type name to set of fields (to bypass python inheritance)
        self._field_cache = {k: {} for k in data_type_map}
        # A set of types which are internally referenced yet not
        # present in the vocabulary
        self._missing_types = set()

    def _load_vocabulary(self):
        if self._vocabulary is None:
            with open(self._vocabulary_file) as vocabulary_file:
                graph = json.load(vocabulary_file)
            self._vocabulary = {node["@id"]: node for node in graph["@graph"]}

    def all_types(self):
        self._load_vocabulary()
        return [
            k.strip().split(":")[-1]
            for k, v in self._vocabulary.items()
            if v["@type"] != "rdf:Property"
        ]

    def load_type(self, name: str):
        "Loads a type and its dependencies from the vocabulary."
        if name in self._type_cache or name in self._missing_types:
            return
        self._load_vocabulary()
        try:
            node = self._vocabulary[f"schema:{name}"]
        except KeyError:
            raise AttributeError(f"Model {name} does not exist")
        # Keep track of forward refs to resolve them afterwards
        forward_refs = set()
        # Collect direct fields from the vocabulary
        fields = {}
        for key, field in (
            (key.strip().split(":")[-1], field)
            for key, field in self._vocabulary.items()
            if field.get("@type") == "rdf:Property"
            if f"schema:{name}" in _setify(field.get("schema:domainIncludes"))
        ):
            declared_field_types = sorted(
                [
                    type_.strip().split(":")[-1]
                    for type_ in _setify(field["schema:rangeIncludes"])
                ]
            )
            field_types = [
                type_name
                for type_name in declared_field_types
                if self._prune_to is None
                or type_name in self._type_cache
                or type_name in self._prune_to
            ]
            for field_type in field_types:
                if f"schema:{field_type}" not in self._vocabulary:
                    self._missing_types.add(field_type)
                elif field_type not in self._type_cache:
                    forward_refs.add(field_type)
            pydantic_type = tuple(
                data_type_map[field_type]
                if field_type in data_type_map
                else f"'{field_type}'"
                for field_type in sorted(
                    field_types,
                    key=lambda field_type: self._type_specificity.get(field_type, 0),
                    reverse=True,
                )
                if field_type not in self._missing_types
            )
            # If any type is explicitly excluded, then add 'Any' to account for them
            if declared_field_types != field_types:
                pydantic_type = pydantic_type + ("Any",)
            type_tuple = ", ".join(pydantic_type)
            # If none was excluded but also none was found, the field may be omitted
            if not pydantic_type:
                continue
            # If there's more than one type there, then build a Union
            elif len(pydantic_type) > 1:
                optional = pydantic_type[-1] != "Any"
                pydantic_type = f"Union[Union[{type_tuple}], List[Union[{type_tuple}]]]"
                if optional:
                    pydantic_type = f"Optional[{pydantic_type}]"
            # If there's only one, then don't build a Union
            else:
                pydantic_type = (
                    type_tuple
                    if type_tuple == "Any"
                    else f"Optional[Union[{type_tuple}, List[{type_tuple}]]]"
                )
            # Register the field
            fields[key] = Field(
                key,
                pydantic_type,
                self._vocabulary[f"schema:{key}"].get("rdfs:comment", ""),
            )

        # Register type-exclusive fields
        self._field_cache[name] = fields
        # Collect parent classes
        parent_names = set(
            reference.strip().split(":")[-1]
            for reference in _setify(node.get("rdfs:subClassOf", []))
        )
        for parent_name in parent_names:
            try:
                self.load_type(parent_name)
            except AttributeError:
                self._missing_types.add(parent_name)
        # Merge in parent fields
        for parent_name in parent_names:
            if parent_name not in self._missing_types:
                self._field_cache[name].update(self._field_cache[parent_name])
        # Register the requested model
        self._type_cache[name] = Model(
            name, node.get("rdfs:comment", ""), self._field_cache[name].values()
        )
        # Resolve the field types
        for forward_ref in forward_refs:
            self.load_type(forward_ref)
        # Resolve type inhabitants
        for member in (
            key.strip().split(":")[-1]
            for key, type_ in self._vocabulary.items()
            if f"schema:{name}" in _setify(type_.get("@type"), prop=None)
        ):
            self._enums[name] = self._enums.get(
                name, Enum(name, node.get("rdfs:comment", ""), [])
            )
            self._enums[name].members.append(member)
            self.load_type(member)

    def models(self):
        "Return all currently loaded models."
        return sorted(
            [
                type_
                for name, type_ in self._type_cache.items()
                if isinstance(type_, Model)
                if name not in self._enums
                if not any(name in enum.members for enum in self._enums.values())
            ],
            key=lambda type_: type_.name,
        )

    def enums(self):
        "Return all currently loaded enums."
        return sorted(self._enums.values(), key=lambda enum: enum.name)


def main(
    models: List[str] = typer.Argument(
        ...,
        help="List of models to target for generation. The tree will be "
        "pruned for these models. Specify 'all' to export all schema.org models.",
    ),
    greedy: bool = typer.Option(
        False,
        "--greedy",
        help="Whether to gulp the model tree recursively, meaning models "
        "will be gathered from the field specification in other models. "
        "This option does nothing if the 'all' wildcard is used (since the whole "
        "graph will be included).",
    ),
):
    """Generates a single python source file with pydantic models
    representing schema.org models.

    """
    all_models = "all" in models
    registry = Registry(
        "./schemaorg-current-http.jsonld",
        data_type_map,
        data_type_specificity,
        prune_to=None if greedy or all_models else models,
    )
    models = models if not all_models else registry.all_types()
    for type_ in models:
        registry.load_type(type_)
    with open("./models.py.tpl") as template_file:
        template = jinja_environment.from_string(template_file.read())
    print(
        black.format_str(
            template.render(
                schemaorg_version=os.getenv("SCHEMAORG_VERSION"),
                commit=os.getenv("COMMIT"),
                typer_version=typer.__version__,
                jinja2_version=jinja2.__version__,
                black_version=black.__version__,
                timestamp=datetime.datetime.now(),
                models=registry.models(),
                enums=registry.enums(),
            ),
            mode=black.Mode(),
        )
    )


if __name__ == "__main__":
    typer.run(main)
