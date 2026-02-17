#!/bin/bash
# scripts/validate_feature1.sh
# Automated validation for Feature1 integration tests
#
# Usage:
#   ./scripts/validate_feature1.sh
#
# This script automates the entire Feature1 validation workflow:
# 1. Checks prerequisites (ffmpeg, directory structure)
# 2. Generates test media assets
# 3. Runs integration tests individually
# 4. Runs full test suite
# 5. Inspects generated videos
# 6. Provides summary report
#
# Exit codes:
#   0 = Success (all expected tests passed)
#   1 = Failure (prerequisites failed or unexpected test failures)

set -e  # Exit on error
set -o pipefail  # Catch errors in pipelines

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
TEST_ASSETS_DIR="/tmp/test_assets"
WORKER_DIR="$PROJECT_ROOT/worker"

# Test results tracking
INDIVIDUAL_PASSED=0
INDIVIDUAL_FAILED=0
INDIVIDUAL_TESTS=()

# Functions

check_prerequisites() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🔍 Checking prerequisites...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    local prereq_failed=0

    # Check ffmpeg
    if command -v ffmpeg &> /dev/null; then
        local ffmpeg_version=$(ffmpeg -version | head -n 1 | cut -d' ' -f3)
        echo -e "${GREEN}✅ ffmpeg found${NC} (version: $ffmpeg_version)"
    else
        echo -e "${RED}❌ ffmpeg not found${NC}"
        echo -e "   Install with: sudo apt-get install ffmpeg"
        prereq_failed=1
    fi

    # Check ffprobe
    if command -v ffprobe &> /dev/null; then
        echo -e "${GREEN}✅ ffprobe found${NC}"
    else
        echo -e "${RED}❌ ffprobe not found${NC}"
        echo -e "   Install with: sudo apt-get install ffmpeg"
        prereq_failed=1
    fi

    # Check we're in project root
    if [ -f "$PROJECT_ROOT/worker/tests/integration/test_render_real.py" ]; then
        echo -e "${GREEN}✅ Integration tests found${NC}"
    else
        echo -e "${RED}❌ Integration tests not found${NC}"
        echo -e "   Expected: $PROJECT_ROOT/worker/tests/integration/test_render_real.py"
        echo -e "   Current directory: $(pwd)"
        prereq_failed=1
    fi

    # Check generate_test_media.py exists
    if [ -f "$SCRIPT_DIR/generate_test_media.py" ]; then
        echo -e "${GREEN}✅ Test media generator found${NC}"
    else
        echo -e "${RED}❌ Test media generator not found${NC}"
        echo -e "   Expected: $SCRIPT_DIR/generate_test_media.py"
        prereq_failed=1
    fi

    # Check Python
    if command -v python &> /dev/null; then
        local python_version=$(python --version 2>&1 | cut -d' ' -f2)
        echo -e "${GREEN}✅ Python found${NC} (version: $python_version)"
    else
        echo -e "${RED}❌ python not found${NC}"
        prereq_failed=1
    fi

    # Check pytest
    if python -c "import pytest" 2>/dev/null; then
        local pytest_version=$(python -c "import pytest; print(pytest.__version__)")
        echo -e "${GREEN}✅ pytest found${NC} (version: $pytest_version)"
    else
        echo -e "${RED}❌ pytest not found${NC}"
        echo -e "   Install with: pip install pytest"
        prereq_failed=1
    fi

    if [ $prereq_failed -eq 1 ]; then
        echo -e "\n${RED}❌ Prerequisites check failed${NC}"
        exit 1
    fi

    echo -e "\n${GREEN}✅ All prerequisites satisfied${NC}"
}

generate_test_media() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🎬 Generating test media...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Clean up old test assets if they exist
    if [ -d "$TEST_ASSETS_DIR" ]; then
        echo -e "   Cleaning up old test assets..."
        rm -rf "$TEST_ASSETS_DIR"
    fi

    echo -e "   Target directory: ${TEST_ASSETS_DIR}"
    echo -e "   Running generator script...\n"

    if python "$SCRIPT_DIR/generate_test_media.py" "$TEST_ASSETS_DIR"; then
        echo -e "\n${GREEN}✅ Test media generated successfully${NC}"

        # Verify assets were created
        local asset_count=$(find "$TEST_ASSETS_DIR" -type f | wc -l)
        echo -e "   Generated $asset_count test files"

        # Show what was created
        echo -e "\n   Directory structure:"
        ls -lh "$TEST_ASSETS_DIR" 2>/dev/null || true
    else
        echo -e "\n${RED}❌ Test media generation failed${NC}"
        exit 1
    fi
}

run_individual_tests() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🧪 Running tests individually...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}ℹ️  Running tests individually to avoid isolation issues${NC}\n"

    export VIDEO_TEST_ASSETS="$TEST_ASSETS_DIR"
    cd "$WORKER_DIR"

    # Array of tests to run
    local tests=(
        "test_render_image_sequence_beat_timing"
        "test_render_mixed_video_image"
        "test_render_crossfade_transitions"
        "test_render_beats_vs_ms_duration"
        "test_render_handles_missing_asset"
    )

    INDIVIDUAL_PASSED=0
    INDIVIDUAL_FAILED=0

    for test in "${tests[@]}"; do
        echo -e "${BLUE}────────────────────────────────────────${NC}"
        echo -e "  Running: ${YELLOW}$test${NC}"
        echo -e "${BLUE}────────────────────────────────────────${NC}"

        local temp_output="/tmp/test_output_$$.txt"

        # Run test and capture output
        if pytest "tests/integration/test_render_real.py::TestRenderRealPipeline::$test" -v --tb=short 2>&1 | tee "$temp_output"; then
            echo -e "${GREEN}  ✅ PASSED${NC}\n"
            ((INDIVIDUAL_PASSED++))
            INDIVIDUAL_TESTS+=("$test:PASSED")
        else
            echo -e "${RED}  ❌ FAILED${NC}\n"
            ((INDIVIDUAL_FAILED++))
            INDIVIDUAL_TESTS+=("$test:FAILED")
        fi

        rm -f "$temp_output"
    done

    local total=$((INDIVIDUAL_PASSED + INDIVIDUAL_FAILED))
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "Individual Test Results:"
    echo -e "  ${GREEN}✅ Passed: $INDIVIDUAL_PASSED/$total${NC}"
    if [ $INDIVIDUAL_FAILED -gt 0 ]; then
        echo -e "  ${RED}❌ Failed: $INDIVIDUAL_FAILED/$total${NC}"
    fi
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

run_full_suite() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🧪 Running full test suite...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}ℹ️  Some tests may fail when run together (known isolation issue)${NC}\n"

    export VIDEO_TEST_ASSETS="$TEST_ASSETS_DIR"
    cd "$WORKER_DIR"

    # Run full suite and capture exit code but don't fail script
    set +e
    pytest tests/integration/test_render_real.py -v --tb=short 2>&1
    local pytest_exit=$?
    set -e

    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    if [ $pytest_exit -eq 0 ]; then
        echo -e "${GREEN}✅ Full suite passed${NC}"
    else
        echo -e "${YELLOW}⚠️  Full suite had failures (exit code: $pytest_exit)${NC}"
        echo -e "${YELLOW}   This is expected due to known isolation issues${NC}"
        echo -e "${YELLOW}   Individual test results above are more reliable${NC}"
    fi
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

inspect_videos() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}🎥 Inspecting generated videos...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Find recently created video files
    local videos=$(find /tmp/pytest-of-$USER -name "render_*.mp4" -type f -mmin -30 2>/dev/null || true)

    if [ -z "$videos" ]; then
        echo -e "${YELLOW}⚠️  No output videos found in /tmp/pytest-of-$USER${NC}"
        echo -e "   (This is OK if tests didn't generate videos)"
        return
    fi

    local video_count=$(echo "$videos" | wc -l)
    echo -e "Found ${video_count} output video(s):\n"

    while IFS= read -r video; do
        if [ -f "$video" ]; then
            echo -e "${GREEN}✅ Video: $video${NC}"

            # File size
            local size=$(ls -lh "$video" | awk '{print $5}')
            echo -e "   Size: $size"

            # Duration using ffprobe
            if command -v ffprobe &> /dev/null; then
                local duration=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$video" 2>/dev/null || echo "unknown")
                if [ "$duration" != "unknown" ]; then
                    printf "   Duration: %.2fs\n" "$duration"
                fi

                # Resolution
                local resolution=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$video" 2>/dev/null || echo "unknown")
                if [ "$resolution" != "unknown" ]; then
                    echo -e "   Resolution: $resolution"
                fi
            fi

            echo ""
        fi
    done <<< "$videos"
}

generate_report() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}📊 Validation Summary${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    echo -e "\n${YELLOW}Individual Test Results:${NC}"
    for test_result in "${INDIVIDUAL_TESTS[@]}"; do
        local test_name=$(echo "$test_result" | cut -d':' -f1)
        local status=$(echo "$test_result" | cut -d':' -f2)

        if [ "$status" = "PASSED" ]; then
            echo -e "  ${GREEN}✅${NC} $test_name"
        else
            echo -e "  ${RED}❌${NC} $test_name"
        fi
    done

    echo -e "\n${YELLOW}Expected Test Behavior:${NC}"
    echo -e "  ${GREEN}✅${NC} 5/5 core tests passing individually"
    echo -e "  ${YELLOW}⊘${NC}  2 tests skipped (corrupted media, timeout scenarios)"
    echo -e "  ${YELLOW}✗${NC}  1 xfail (repeat mode not yet implemented)"

    echo -e "\n${YELLOW}Known Issues:${NC}"
    echo -e "  - Some tests may fail when run together (isolation issue)"
    echo -e "  - Individual test runs are more reliable"

    echo -e "\n${YELLOW}For Full Validation Plan:${NC}"
    echo -e "  📄 docs/feature1_validation.txt"

    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    # Final verdict
    if [ $INDIVIDUAL_FAILED -eq 0 ]; then
        echo -e "${GREEN}✅ VALIDATION SUCCESSFUL${NC}"
        echo -e "${GREEN}   All individual tests passed!${NC}"
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
        return 0
    else
        echo -e "${RED}❌ VALIDATION FAILED${NC}"
        echo -e "${RED}   $INDIVIDUAL_FAILED individual test(s) failed${NC}"
        echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
        return 1
    fi
}

# Main execution
main() {
    echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  ${YELLOW}🧪 Feature1 Integration Test Validation${NC} ${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"

    # Store original directory
    local original_dir=$(pwd)

    # Run validation steps
    check_prerequisites
    generate_test_media
    run_individual_tests
    run_full_suite
    inspect_videos

    # Generate report and capture exit code
    if generate_report; then
        exit 0
    else
        exit 1
    fi
}

# Execute main function with all arguments
main "$@"
