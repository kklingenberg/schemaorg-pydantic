# schemaorg-pydantic

This is a docker image which generates a python source file with
[pydantic](https://pydantic-docs.helpmanual.io/) models which follow
[schema.org](https://schema.org) types.

## How to use

Check the help page:

```bash
docker run --rm plotter/schemaorg-pydantic --help
```

Which should give you something like this:

```
Usage: generate.py [OPTIONS] MODELS...

  Generates a single python source file with pydantic models representing
  schema.org models.

Arguments:
  MODELS...  List of models to target for generation. The tree will be pruned
             for these models. Specify 'all' to export all schema.org models.
             [required]


Options:
  --greedy                        Whether to gulp the model tree recursively,
                                  meaning models will be gathered from the
                                  field specification in other models. This
                                  option does nothing if the 'all' wildcard is
                                  used (since the whole graph will be
                                  included).  [default: False]

  --install-completion [bash|zsh|fish|powershell|pwsh]
                                  Install completion for the specified shell.
  --show-completion [bash|zsh|fish|powershell|pwsh]
                                  Show completion for the specified shell, to
                                  copy it or customize the installation.

  --help                          Show this message and exit.
```

## Examples

To generate a source file for models
[Product](https://schema.org/Product) and
[Brand](https://schema.org/Brand):

```bash
docker run --rm plotter/schemaorg-pydantic Product Brand > models.py
```

To generate a source file for those same models, but also pulling all
dependent models as well:

```bash
docker run --rm plotter/schemaorg-pydantic --greedy Product Brand > greedy_models.py
# The generated file's size is 2.2M !
```

To generate a source file for all of the models possibly contained
within the schema.org vocabulary:

```bash
docker run --rm plotter/schemaorg-pydantic all > all_models.py
# The generated file's size is 16M !!!
```

## Answers to imaginary questions

> Is it any good?

Pydantic is excellent. This thing, I'll need to test for a while and
see. It'll probably come down to manually editing the generated source
files and then pondering whether doing it all manually was more
sensible in the end.

> Is there something similar to this that's more mature?

Yes. If you're interested in schema.org, there's openschemas'
[schemaorg](https://github.com/openschemas/schemaorg) library. It
doesn't generate pydantic models, but does many wonderful things like
custom schema generation. Plus, it should be simple to create pydantic
models from `Schema` objects through pydantic's
[create_model](https://pydantic-docs.helpmanual.io/usage/models/#dynamic-model-creation)
function.

If you're more interested in simply encoding models externally and
generating pydantic source files, then there's
[datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator/).

> What's with the weird `locals().update()` thing at the end of each model?

This is simply a means to disambiguate models, inspired by JSON-LD's
type markers. The reason it's written horrendously like that is
because pydantic's aliases didn't quite work on the disambiguation
part (I don't know why), and I really wanted a field named `@type`,
which isn't a valid python variable name. Hence the local namespace
injection and not simply a:

```python
type_: Literal["Thing"] = Field("Thing", alias="@type", const="Thing")
```

I tried that, but it didn't pass the disambiguation tests.

> Why generate source code through string templates?

It's just easier to do than AST assembly. Plus, the
[ast.unparse()](https://docs.python.org/3.9/library/ast.html#ast.unparse)
doesn't quite generate readable code.
