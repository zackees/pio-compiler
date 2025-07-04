Add a examples/** as an input type.

Right now we have

uv run tpo examples/Blink

But if we want to run multiple sketches we would need one tool call per invocation.

This change allows

uv run tpo examples/** which will compile all ino directories.

This will end up using the multi_compile feature to compile all of these tests in parallel.