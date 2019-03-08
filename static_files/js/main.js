

const root_node_name = '{root}';
var tree_dir_state = 'dirs';

//--------------- For Tree/Dir Indicator -----------------

function toggle_tree_dir() {
    var toggle_tree = jQuery('#toggle-tree');
    var toggle_dir  = jQuery('#toggle-dir');

    if (tree_dir_state == 'dirs') {
        tree_dir_state = 'trees';
        toggle_tree.removeClass('toggle-red');
        toggle_tree.addClass('toggle-green');
        toggle_dir.removeClass('toggle-green');
        toggle_dir.addClass('toggle-red');
    } else {
        tree_dir_state = 'dirs';
        toggle_tree.removeClass('toggle-green');
        toggle_tree.addClass('toggle-red');
        toggle_dir.removeClass('toggle-red');
        toggle_dir.addClass('toggle-green');
    }
}


// --------------- For Browse List -----------------

function browseListChanges(first, second) {
    let jst = jQuery('#browselist').jstree();
    var selected_paths = [];
    for(let x = 0; x < second.selected.length; x++) {
        const node = jst.get_node(second.selected[x]);
        var path = jst.get_path(node);
        path.shift(); // remove root
        // if a file was selected, remove the end of the array to just have directory
        if (node.icon == 'jstree-file') path.pop()
        selected_paths.push(path.join('/'));
    }
    const component = jQuery('#selectedDirs');
    component.val(selected_paths.join(','));
}


function showbl_callback(data) {
    let tree_struct = JSON.parse(data);
    tree_struct.plugins = ["changed", "wholerow"];
    let component = jQuery('#browselist');
    component.on('select_node.jstree', browseListChanges);
    component.on('deselect_node.jstree', browseListChanges);
    component.jstree(tree_struct);
};

function showBrowseList() {
    jQuery.get('/browselist', {}, showbl_callback);
}

// -------------- Handling navbar labels field -----------------------------------

// We need to have an up-to-date list of labels from the database.
// Start with copy here (at loading) and then update it whenever
// we are about editing the labels.
function refresh_labels_cb(data) {
    labels = JSON.parse(data);
}

function refresh_labels() {
    jQuery.get('/labels', {}, refresh_labels_cb);
}

refresh_labels();  // do it now

function custom_matcher(request, response) {
    const request_term = $.ui.autocomplete.escapeRegex(request.term);
    const elements = request_term.toString().split('\\,');
    const last_input = elements[elements.length-1];
    var completed = '';
    for (let i = 0; i < elements.length - 1; i++) {
        completed += elements[i] + ',';
    }
    var matcher = new RegExp("^" + last_input, "i");
    var results = $.grep(labels, function(item) {
             return matcher.test(item);
    });
    // append the other, already-complete labels (comma delimited)
    for (let i = 0; i < results.length; i++) {
        results[i] = completed + results[i];
    }
    response(results);
};

// Register a click listener
const selected_labels = jQuery('#selectedLabels');

jQuery( function register() {
    selected_labels.autocomplete({ source: custom_matcher});
});



// ---------- For main search ------------------------------

function search_callback(data) {
    // console.log('search results:\n'+data);
    var main = jQuery('#main_section')
    main.empty()
    main.append(data);
};

function do_main_search() {
    var labels = jQuery('#selectedLabels').val().toLowerCase();
    var dirs = jQuery('#selectedDirs').val();
    if (labels === '')  labels = undefined;
    if (dirs === '') dirs = undefined;
    var uri_string = '/search';
    var sep = '?';
    if (dirs !== undefined) {
        uri_string += sep + tree_dir_state + '=' + dirs;
        sep = '&';
    } else {
        uri_string += sep + tree_dir_state + '=';
        sep = '&';
    }
    if (labels != undefined) {
        uri_string += sep + 'labels=' + labels;
    }
    const url = encodeURI(uri_string);
    jQuery.get(url, {}, search_callback);
}


// ---------- For adding/removing labels from items --------

var active_item_id;  // keeps track of what we are working on
const add_labels_modal = jQuery('#add_label_modal');

// Set up autocomplete for the add label modal dialog for adding labels to items
const add_a_label_input = jQuery('#add_a_label_input');

jQuery( function register2() {
    add_a_label_input.autocomplete({ source: custom_matcher});
});

// setup focus on modal shown event
add_labels_modal.on('shown.bs.modal', function() {
    add_a_label_input.focus();
} );

// handle pressing enter in add label input
$('#add_a_label_input').keyup( function(event) {
    if (event.keyCode === 13) finish_add_a_label(); } );

function start_add_a_label(item_id) {
    if (item_id.slice(0,7) != 'search-') {
        alert(`problem here with item_id of ${item_id}`);
    } else {
        active_item_id = item_id.slice(7, item_id.length);
        // add_a_label_input[0].focus();
        // docoument.getElementById("add_a_label_input").focus();
        // add_a_label_input.setCursorPosition = 0;
    }
}

function finish_add_a_label() {
    add_labels_modal.modal('toggle');
    const newlabels = add_a_label_input[0].value.toLowerCase();
    add_a_label_input[0].value = '';  // clear it for next time
    jQuery.get('/add_label?item_id=' + active_item_id + ';labels=' + newlabels);
    // add to search results
    const labels_span_id = `#labels-for-${active_item_id}`;
    const labels_span = $(labels_span_id);
    var prefix = '';
    // determine if there are existing labels
    // console.log(`labels_span children length = ${labels_span.children().length}`);
    if (labels_span.children().length > 0) prefix = ', ';
    var label_key;
    var labels_str = ''; // build this incrementally for each label
    newlabels.split(',').forEach(function(label) {
        label_key = `search-${active_item_id}-${label}`;
        labels_str += `<span id="${label_key}">${prefix}${label}<span class="ml-1">`
                      + '<img src="/static_files/img/x-button.png" width="16px" '
                      + "onclick=\"remove_a_label('" + label_key + "')\"></span></span>";
        prefix = ', ';  // subsequently, separate with comma + space
    });
    // insert the new html into the page before the Add button
    labels_span.append(labels_str);
}

function cancel_add_a_label() {
    add_labels_modal.modal('toggle');
    add_a_label_input.value = '';
}

function remove_a_label(label_id) {
    // remove from GUI
    const idselector = "#" + label_id;
    $(idselector).remove();

    // removing the comma-space from the first label if just deleted the first one.
    // work backwards from the label_id, a string of the form search-#-label, where
    // # is the item number. We need just that number
    const regexp3 = /search-([^-]+)-.*/;
    const number = regexp3.exec(label_id)[1];
    if (number !== null) {
        var remaining_labels = get_labels(number);
        const first_label_key = `#search-${number}-${remaining_labels[0]}`;
        if ($(first_label_key).length > 0) {

            var txt = $(first_label_key)[0].firstChild.textContent;
            if (txt !== undefined && /, .*/.exec(txt) !== null) {
                $(first_label_key)[0].firstChild.textContent = txt.replace(/^, /, '');
            }
        }
    }
    // remove from database
    jQuery.get('/remove_label?id=' + label_id);
    refresh_labels();
}

// Bulk selection and operations ---------------------------------------------------------------------------

const bulk_action_modal = jQuery('#bulk_action_modal');
const bulk_action_input = $('#bulk_action_label_input');

// setup focus on modal shown
bulk_action_modal.on('shown.bs.modal', function() {
    bulk_action_input.focus();
});

jQuery( function register3() {
    bulk_action_input.autocomplete({ source: custom_matcher});
});

function enter_handler_bulk(event) {
    if (event.keyCode === 13) {
        finish_bulk_action();
    }
}
// handle pressing enter in bulk action label input
bulk_action_input.keyup(enter_handler_bulk);

function mark_selected() {
    var cla, path, n;
    var results = new Array();
    var regexp1 = /path-([0-9]+)/;
    var sel = getSelection();
    // gets the JavaScript DOM node to test for inclusion in selection
    var all_paths = $('.bigpath').get();
    for (path of all_paths) {
        if (sel.containsNode(path)) {
            for (cla of path.classList) {
                n = regexp1.exec(cla);
                if (n !== null) { results.push(n[1]); }
            }
        }
    }
    // console.log(results);
}

function mark_all() {
    // handle the onchange event for the mark/unmark all checkbox
    var action;
    if ($('#checkbox-for-all')[0].checked) {
        action = 'set';
    } else {
        action = 'unset';
    }
    $('.item-checkbox').each( function (index, item) {
        if (action === 'set' && ! item.checked) {
            item.click();
        } else if (action === 'unset' && item.checked) {
            item.click();
        }
    })
}

function find_marked() {
    const regexp2 = /checkbox-for-([0-9]+)/;
    var results = new Array();
    var n;
    $('.item-checkbox').each( function (index, item) {
        if (item.checked) {
            n = regexp2.exec(item.id);
            results.push(n[1]);
        }
    })
    return(results);
}

function check_bulk_action() {
    var marked = find_marked();
    if (marked.length === 0) {
        alert('nothing marked');
        return;
    }
    bulk_action_modal.modal('toggle');

}

function get_labels(item) {
    // take an item which is a string of an *integer* ("4") for the item in search results
    // and return all current labels
    const labels_span_id = '#labels-for-' + item;
    const labels_span = $(labels_span_id);
    const span_id_prefix = `search-${item}-`;
    var results = new Array();

    labels_span.children().each(function(index, span_element) {
        var label = span_element.id;
        // verify the string starts with span_id_prefix and then remove that part to leave the label itself
        if (label.startsWith(span_id_prefix)) {
            results.push(label.substring(span_id_prefix.length));
        } else {
            console.log(`What am I supposed to do with this label span id: ${label}?`);
        }
    })

    return(results);
}


function finish_bulk_action() {
    var marked_item;
    var marked = find_marked();
    // (bulk_action_input[0].value);
    const new_labels = bulk_action_input[0].value.toLowerCase().split(',');

    // first order of business, is to determine which of the labels provided is
    // currently used. We will ask the GUI that info.
    var use_chart = {};
    for (marked_item of marked) {
        var item_labels = get_labels(marked_item);
        var found_labels = new Array();
        for (var n of new_labels) {
            if (item_labels.includes(n)) {
                found_labels.push(true);
            } else {
                found_labels.push(false);
            }
        }
        use_chart[marked_item] = found_labels;
    }


    // if adding new labels
    if ( $('#bulk-radio-add')[0].checked ) {

        for (marked_item of marked) {
            var copy_new_labels = new_labels.slice();
            var uc = use_chart[marked_item];

            // traverse the list in reverse order so we can remove labels from the
            // array in a loop
            for (var i = copy_new_labels.length - 1; i >= 0; i--) {
                // if we are going to add a label that already exists, lets skip that;
                if (uc[i]) {
                    // this one already present - remove from array
                    copy_new_labels.splice(i, 1);
                }
            }
            // store new labels in the database
            jQuery.get('/add_label?item_id=' + marked_item + ';labels=' + copy_new_labels);

            // add new labels to search results
            var labels_span_id = `#labels-for-${marked_item}`;
            var labels_span = $(labels_span_id);
            var prefix = '';
            // determine if there are existing labels
            if (labels_span.children().length > 0) prefix = ', ';
            var label_key;
            var labels_str = ''; // build this incrementally for each label
            copy_new_labels.forEach(function(label) {
                label_key = `search-${marked_item}-${label}`;
                labels_str += `<span id="${label_key}">${prefix}${label}<span class="ml-1">`
                              + '<img src="/static_files/img/x-button.png" width="16px" '
                              + "onclick=\"remove_a_label('" + label_key + "')\"></span></span>";
                prefix = ', ';  // for subsequent labels separate with comma + space
            });
            // insert the new html into the page before the Add button
            labels_span.append(labels_str);
        }

    } else {  // deleting the labels

        for (marked_item of marked) {
            var copy_new_labels = new_labels.slice();
            var uc = use_chart[marked_item];

            // traverse the list in reverse order so we can remove labels from the
            // array in a loop
            for (var i = copy_new_labels.length - 1; i >= 0; i--) {
                // if we are going to delete a label that doesn't exist, lets skip that;
                if (! uc[i]) {
                    // this one already present - remove from array
                    copy_new_labels.splice(i, 1);
                }
            }

            copy_new_labels.forEach(function(label) {
                var label_key = `search-${marked_item}-${label}`;
                remove_a_label(label_key);
            })
        }
    }

    bulk_action_modal.modal('toggle');
    bulk_action_input[0].value = '';  // clear for next go-around
}

function cancel_bulk_action() {
    bulk_action_input[0].value = '';  // clear for next go-around
}


/* ---------- Notes for reference --------------------------
  modifying element class
  document.getElementById(menu_state).style = 'display:none';
  var classparts = document.getElementById(menu_link).classList;
  classparts.remove('active');
  document.getElementById(menu_link).classList = classparts;
*/

     