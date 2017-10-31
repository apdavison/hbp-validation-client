import os
import json
import webbrowser


def view_json_tree(data):
    """
    Displays the JSON tree structure inside the web browser
    """
    _make_js_file(data)

    script_dir = os.path.dirname(__file__)
    rel_path = "jsonTreeViewer/index.htm"
    abs_file_path = os.path.join(script_dir, rel_path)
    webbrowser.open(abs_file_path, new=2)

def _make_js_file(data):
    """
    Creates a JavaScript file from give JSON object; loaded by the browser
    This eliminates cross-origin issues with loading local data files (e.g. via jQuery)
    """

    script_dir = os.path.dirname(__file__)
    rel_path = "jsonTreeViewer/data.js"
    abs_file_path = os.path.join(script_dir, rel_path)
    with open(abs_file_path, 'w') as outfile:
        outfile.write("var data = '")
        json.dump(data, outfile)
        outfile.write("'")
