@tool
extends McpTestSuite

const RUNNER_PATH := "res://addons/godot_ai/utils/update_activation_runner.gd"
const PLUGIN_CFG := "res://addons/godot_ai/plugin.cfg"


func suite_name() -> String:
	return "update_activation"


func test_file_backed_runner_cannot_disable_the_editor_plugin() -> void:
	var runner: Node = load(RUNNER_PATH).new()
	Engine.get_main_loop().root.add_child(runner)
	var enabled := EditorInterface.is_plugin_enabled(PLUGIN_CFG)
	var accepted: bool = runner.call("start", _package())
	assert_false(accepted, "a runner whose source can be replaced must refuse activation")
	assert_eq(EditorInterface.is_plugin_enabled(PLUGIN_CFG), enabled)
	runner.free()


func test_incomplete_handoff_leaves_the_live_plugin_untouched() -> void:
	var script := GDScript.new()
	script.source_code = FileAccess.get_file_as_string(RUNNER_PATH)
	var error := script.reload()
	assert_eq(error, OK, "independent activation source must compile")
	if error != OK:
		return
	var enabled := EditorInterface.is_plugin_enabled(PLUGIN_CFG)
	var wrong_path := _package()
	wrong_path.stage_root = "res://addons/other_plugin"
	var missing_hash := _package()
	missing_hash.record.erase("expected_tree_sha256")
	var wrong_authority_type := _package()
	wrong_authority_type.record.replace_owned_mismatches = "true"
	for package in [{}, wrong_path, missing_hash, wrong_authority_type]:
		var runner: Node = script.new()
		Engine.get_main_loop().root.add_child(runner)
		assert_false(runner.call("start", package), "incomplete handoff must be refused")
		assert_eq(EditorInterface.is_plugin_enabled(PLUGIN_CFG), enabled)
		runner.free()


func _package() -> Dictionary:
	return {
		"stage_root": "res://addons/.godot_ai_update/stage/addons/godot_ai",
		"record": {
			"from_version": "4.0.4", "to_version": "4.0.5",
			"manifest_sha256": "0".repeat(64), "expected_tree_sha256": "0".repeat(64),
			"editor_nonce": "test", "replace_owned_mismatches": false,
		},
	}
