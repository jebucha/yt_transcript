# Spec Delta

## ADDED Requirements

### Requirement: Result header layout
The interface SHALL render the video title on its own line above the action toolbar, bounding the title's visible height to at most two lines and truncating overflow with a visible ellipsis, while exposing the complete untruncated title as plain text via the title element's DOM text and a hover tooltip attribute. The action toolbar SHALL wrap onto additional lines within the page width instead of narrowing the title into a column beside it.

#### Scenario: Long title stays bounded
- **WHEN** a successful fetch returns a video whose title is far longer than the available header width
- **THEN** the title is displayed above the action toolbar, occupies at most two visible lines with an ellipsis, and does not render as a tall narrow vertical column of text
- **Test Requirement**
  - **ID:** T-WEB-INTERFACE-015
  - **File:** tests/e2e/test_ui.py::test_long_title_stays_bounded
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_long_title_stays_bounded -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Full title available on hover
- **WHEN** a long title is visually truncated
- **THEN** the title element exposes the complete, untruncated title as plain text via its DOM text and a hover tooltip attribute
- **Test Requirement**
  - **ID:** T-WEB-INTERFACE-016
  - **File:** tests/e2e/test_ui.py::test_long_title_tooltip
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_long_title_tooltip -q
  - **Pass:** exit code 0, no skipped tests

#### Scenario: Action toolbar wraps at narrow widths
- **WHEN** the browser viewport is narrower than the width required to place all action toolbar controls on one line
- **THEN** the controls wrap onto additional lines and remain fully visible within the page width, with no horizontal overflow
- **Test Requirement**
  - **ID:** T-WEB-INTERFACE-017
  - **File:** tests/e2e/test_ui.py::test_result_actions_wrap_narrow
  - **Command:** python -m pytest tests/e2e/test_ui.py::test_result_actions_wrap_narrow -q
  - **Pass:** exit code 0, no skipped tests
