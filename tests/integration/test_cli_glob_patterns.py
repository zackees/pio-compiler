"""Test glob pattern support in the CLI."""

import subprocess


class TestCliGlobPatterns:
    """Test glob pattern support for compiling multiple sketches."""

    def test_examples_double_star_pattern(self, tmp_path):
        """Test that examples/** pattern finds and compiles all .ino sketches."""
        # Create test directory structure
        examples_dir = tmp_path / "examples"
        examples_dir.mkdir()

        # Create multiple sketch directories with .ino files
        sketch_dirs = ["Blink", "Fade", "Button", "nested/DeepSketch"]
        created_sketches = []

        for sketch_name in sketch_dirs:
            sketch_dir = examples_dir / sketch_name
            sketch_dir.mkdir(parents=True, exist_ok=True)
            ino_file = sketch_dir / f"{sketch_name.split('/')[-1]}.ino"
            ino_file.write_text("void setup() {} void loop() {}")
            created_sketches.append(sketch_dir)

        # Also create a non-sketch directory that should be ignored
        non_sketch_dir = examples_dir / "docs"
        non_sketch_dir.mkdir()
        (non_sketch_dir / "README.md").write_text("Documentation")

        # Run the CLI with glob pattern
        cmd = f"tpo {examples_dir}/** --native"
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=tmp_path
        )

        # Check that all sketch directories were compiled
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify each sketch was built
        for sketch_dir in created_sketches:
            sketch_name = sketch_dir.name
            assert (
                f"[BUILD] {examples_dir.name}/{sketch_dir.relative_to(examples_dir)}"
                in result.stdout
                or f"[BUILD] examples/{sketch_dir.relative_to(examples_dir)}"
                in result.stdout
            ), f"Expected to find build output for {sketch_name}"

        # Verify non-sketch directory was not compiled
        assert (
            "docs" not in result.stdout
            or "[BUILD]" not in result.stdout.split("docs")[0]
        )

    def test_specific_glob_pattern(self, tmp_path):
        """Test specific glob patterns like examples/B*."""
        # Create test directory structure
        examples_dir = tmp_path / "examples"
        examples_dir.mkdir()

        # Create sketches - some matching B*, some not
        matching_sketches = ["Blink", "Button", "Buzzer"]
        non_matching_sketches = ["Fade", "Servo"]

        all_sketches = matching_sketches + non_matching_sketches

        for sketch_name in all_sketches:
            sketch_dir = examples_dir / sketch_name
            sketch_dir.mkdir()
            ino_file = sketch_dir / f"{sketch_name}.ino"
            ino_file.write_text("void setup() {} void loop() {}")

        # Run the CLI with specific glob pattern
        cmd = f"tpo {examples_dir}/B* --native"
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=tmp_path
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify only B* sketches were built
        for sketch_name in matching_sketches:
            assert (
                sketch_name in result.stdout
            ), f"Expected to find {sketch_name} in output"

        for sketch_name in non_matching_sketches:
            # These should not appear in BUILD lines
            build_lines = [
                line for line in result.stdout.split("\n") if "[BUILD]" in line
            ]
            for line in build_lines:
                assert (
                    sketch_name not in line
                ), f"Did not expect to find {sketch_name} in build output"

    def test_multiple_glob_patterns(self, tmp_path):
        """Test multiple glob patterns in one command."""
        # Create test directory structure
        examples_dir = tmp_path / "examples"
        tests_dir = tmp_path / "tests"
        examples_dir.mkdir()
        tests_dir.mkdir()

        # Create sketches in different directories
        example_sketches = ["Blink", "Fade"]
        test_sketches = ["TestSerial", "TestSPI"]

        for sketch_name in example_sketches:
            sketch_dir = examples_dir / sketch_name
            sketch_dir.mkdir()
            ino_file = sketch_dir / f"{sketch_name}.ino"
            ino_file.write_text("void setup() {} void loop() {}")

        for sketch_name in test_sketches:
            sketch_dir = tests_dir / sketch_name
            sketch_dir.mkdir()
            ino_file = sketch_dir / f"{sketch_name}.ino"
            ino_file.write_text("void setup() {} void loop() {}")

        # Run the CLI with multiple glob patterns
        cmd = f"tpo {examples_dir}/* {tests_dir}/* --native"
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=tmp_path
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify all sketches were built
        all_sketches = example_sketches + test_sketches
        for sketch_name in all_sketches:
            assert (
                sketch_name in result.stdout
            ), f"Expected to find {sketch_name} in output"

    def test_glob_no_matches(self, tmp_path):
        """Test glob pattern that matches no sketches."""
        # Create test directory structure but no matching sketches
        examples_dir = tmp_path / "examples"
        examples_dir.mkdir()

        # Run the CLI with glob pattern that matches nothing
        cmd = f"tpo {examples_dir}/Z* --native"
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=tmp_path
        )

        # Should fail with appropriate error message
        assert result.returncode == 1
        assert (
            "No sketches found matching pattern" in result.stderr
            or "Sketch path does not exist" in result.stderr
        )

    def test_mixed_glob_and_direct_paths(self, tmp_path):
        """Test mixing glob patterns with direct paths."""
        # Create test directory structure
        examples_dir = tmp_path / "examples"
        examples_dir.mkdir()

        # Create sketches
        glob_sketches = ["Blink", "Button"]
        for sketch_name in glob_sketches:
            sketch_dir = examples_dir / sketch_name
            sketch_dir.mkdir()
            ino_file = sketch_dir / f"{sketch_name}.ino"
            ino_file.write_text("void setup() {} void loop() {}")

        # Create a direct path sketch
        direct_sketch_dir = tmp_path / "MySketch"
        direct_sketch_dir.mkdir()
        (direct_sketch_dir / "MySketch.ino").write_text(
            "void setup() {} void loop() {}"
        )

        # Run the CLI with mixed patterns
        cmd = f"tpo {examples_dir}/B* {direct_sketch_dir} --native"
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, cwd=tmp_path
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify all expected sketches were built
        assert "Blink" in result.stdout
        assert "Button" in result.stdout
        assert "MySketch" in result.stdout
        assert "Fade" not in result.stdout  # This one shouldn't be built
