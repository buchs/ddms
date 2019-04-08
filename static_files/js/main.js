

const refresh_interval = 60; // seconds
const root_node_name = '{root}';
var tree_dir_state = 'dirs';

//--------------- General Helpers ------------------------
function listProperties(obj) {
   // find class
   console.log('Class: ' + Object.prototype.toString.call(obj));
   var propList = "";
   for(var propName in obj) {
      if(typeof(obj[propName]) != "undefined") {
         propList += (propName + ", ");
      }
   }
   console.log(propList);
}

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
    var main = jQuery('#main_section')
    main.empty()
    main.append(data);
    $('.bigpath').single_double_click(single_click_callback, double_click_callback);
}

function do_main_search(new_search=false) {
    var labels = jQuery('#selectedLabels').val().toLowerCase();
    var dirs = jQuery('#selectedDirs').val();
    if (labels === '')  labels = undefined;
    if (dirs === '') dirs = undefined;
    var uri_string = '/search';
    if (new_search) uri_string = '/search_new';
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

    // Is this a Relate operation?
    if ( $('#bulk-radio-rel')[0].checked ) {
        // For relating items
       if (marked.length != 2) {
           alert('You need to select just two items to Relate them');
       } else {
           var url = `/relate?items=${marked[0]},${marked[1]}`;
           jQuery.get(url); // tell the backend
           // now try updating the GUI...
           var paths = new Array();
           var key, index, item;
           // grab all the paths
           for (index=0; index < 2; index++)
           {
               key = `.path-${marked[index]}`;
               item = $(key);
               paths.push(item[0].textContent);
           }
           // now do editing
           for (index=0; index < 2; index++)
           {
               var other = index ^ 1;
               var html_insert = ''
               var insertion_point = $(`#related-for-${index}`)[0];
               insertion_point.append(paths[other])
           }
       }

    // Else we have label operations
    } else {

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
    }

    bulk_action_modal.modal('toggle');
    bulk_action_input[0].value = '';  // clear for next go-around
}

function cancel_bulk_action() {
    bulk_action_input[0].value = '';  // clear for next go-around
}



// ---------- For adding/removing biblerefs from items --------

// already above --> var active_item_id;  // keeps track of what we are working on
const add_biblerefs_modal = jQuery('#add_bibleref_modal');

// Set up autocomplete for the add bibleref modal dialog for adding biblerefs to items
const add_a_bibleref_input = jQuery('#add_a_bibleref_input');

jQuery( function register2() {
    add_a_bibleref_input.autocomplete({ source: custom_matcher});
});

// setup focus on modal shown event
add_biblerefs_modal.on('shown.bs.modal', function() {
    add_a_bibleref_input.focus();
} );

// handle pressing enter in add bibleref input
$('#add_a_bibleref_input').keyup( function(event) {
    if (event.keyCode === 13) finish_add_a_bibleref(); } );

function start_add_a_bibleref(item_id) {
    if (item_id.slice(0,7) != 'search-') {
        alert(`problem here with item_id of ${item_id}`);
    } else {
        active_item_id = item_id.slice(7, item_id.length);
    }
}

function get_bibleref_number(span_element) {
    // Retrieve the html element id. It will be of the form search-0-BR2  (item 0, Bibleref 2)
    const regexp4 = new RegExp('search-[0-9][0-9]*-BR([0-9][0-9]*)');
    var bibleref_num = regexp4.exec(span_element.id)[1];
    console.log('got bibleref # ' + bibleref_num);
    return bibleref_num;
}

function finish_add_a_bibleref() {

    /* It should be noted again, we will not resuse the numbers of the biblerefs when deleting and then adding
       biblerefs. So we just keep a count of the last one added as an attribute (num) on the span element
       enclosing the biblerefs for a particular search item. Also, noting that the num attribute of the
        bibleref span for a given search item is set to the next available number. So, use it first, then
        increment it for the next use.
    */

    add_biblerefs_modal.modal('toggle');
    const new_biblerefs = add_a_bibleref_input[0].value;
    add_a_bibleref_input[0].value = '';  // clear it for next time
    var get_response = jQuery.get('/add_bibleref?item_id=' + active_item_id + ';biblerefs=' + new_biblerefs);
    console.log('response from /add_bibleref?item_id: ' + get_response);

    // add to search results
    const biblerefs_span_id = `#biblerefs-for-${active_item_id}`;
    const biblerefs_span = $(biblerefs_span_id);
    // retrieve number of existing bibleref slots
    var num_bibleref_slots = biblerefs_span.attr('num');
    // also retrieve the actual number of biblerefs and set prefix on that basis (whether a comma is used)
    var prefix = '';
    if (biblerefs_span.children().length > 0) prefix = ', ';

    var bibleref_key;
    var biblerefs_str = ''; // build this incrementally for each bibleref

    new_biblerefs.split(',').forEach(function(bibleref) {
        bibleref_key = `search-${active_item_id}-BR${num_bibleref_slots}`;
        num_bibleref_slots++;
        biblerefs_str += `<span id="${bibleref_key}">${prefix}${bibleref}<span class="ml-1">`
                      + '<img src="/static_files/img/x-button.png" width="16px" '
                      + "onclick=\"remove_a_bibleref('" + bibleref_key + "')\"></span></span>";
        prefix = ', ';  // subsequently, separate with comma + space
    });

    // insert the new html into the page before the Add button
    biblerefs_span.append(biblerefs_str);
    // and update the attribute of the current number of bibleref slots
    biblerefs_span.attr('num',num_bibleref_slots.toString());
}

function cancel_add_a_bibleref() {
    add_biblerefs_modal.modal('toggle');
    add_a_bibleref_input.value = '';
}

function remove_a_bibleref(bibleref_id) {
    // remove from GUI
    const idselector = "#" + bibleref_id;
    $(idselector).remove();

    // removing the comma-space from the first bibleref if just deleted the first one.
    // work backwards from the bibleref_id, a string of the form search-#-bibleref, where
    // # is the item number. We need just that number
    const regexp3 = /search-([^-]+)-.*/;
    const number = regexp3.exec(bibleref_id)[1];
    if (number !== null) {
        var remaining_biblerefs = get_biblerefs(number);
        const first_bibleref_key = `#search-${number}-${remaining_biblerefs[0]}`;
        if ($(first_bibleref_key).length > 0) {

            var txt = $(first_bibleref_key)[0].firstChild.textContent;
            if (txt !== undefined && /, .*/.exec(txt) !== null) {
                $(first_bibleref_key)[0].firstChild.textContent = txt.replace(/^, /, '');
            }
        }
    }
    // remove from database
    jQuery.get('/remove_bibleref?id=' + bibleref_id);
}


function get_biblerefs(item) {
    // take an item which is a string of an *integer* ("4") for the item in search results
    // and return all current biblerefs
    const biblerefs_span_id = '#biblerefs-for-' + item;
    const biblerefs_span = $(biblerefs_span_id);
    const span_id_prefix = `search-${item}-`;
    var results = new Array();

    biblerefs_span.children().each(function(index, span_element) {
        var bibleref = span_element.id;
        // verify the string starts with span_id_prefix and then remove that part to leave the bibleref itself
        if (bibleref.startsWith(span_id_prefix)) {
            results.push(bibleref.substring(span_id_prefix.length));
        } else {
            console.log(`What am I supposed to do with this bibleref span id: ${bibleref}?`);
        }
    })

    return(results);
}

// -----------------------------------------------------------
// Search by biblerefs

var search_biblerefs_modal = $('#search-biblerefs-modal');
var search_biblerefs_input = $('#search-biblerefs-input');
var search_biblerefs_label_input = $('#search-biblerefs-label-input');

// handle pressing enter in search biblerefs inputs
search_biblerefs_input.keyup( function(event) {
    if (event.keyCode === 13) finish_search_biblerefs(); } );
search_biblerefs_label_input.keyup( function(event) {
    if (event.keyCode === 13) finish_search_biblerefs(); } );


function finish_search_biblerefs() {

    // gui cleanup
    search_biblerefs_modal.modal('toggle');
    const biblerefs = search_biblerefs_input[0].value;
    search_biblerefs_input[0].value = '';  // clear it for next time
    const labels = search_biblerefs_label_input[0].value;
    search_biblerefs_label_input[0].value = '';
    console.log(`labels: ${labels}`);
    // query the backend
    var uri_string = `/search_bible?labels=${labels};biblerefs=${biblerefs}`;
    const url = encodeURI(uri_string);
    console.log(`url: ${url}`);
    jQuery.get(url, {}, search_callback);  // search_callback is the same handler we use for main search above

}


function cancel_search_biblerefs() {
    // just cleanup gui
    search_biblerefs_modal.modal('toggle');
    search_biblerefs_input[0].value = '';
    search_biblerefs_label_input[0].value = '';
}


// -----------------------------------------------------------
// Handle opening items from search results

jQuery.fn.single_double_click = function(single_click_callback, double_click_callback, timeout) {

  var event_source;

  function sdc_outer() {
    var clicks = 0, self = this;
    function sdc_timer() {
       var item_id, item_path;
       for (itsclass of event_source.target.classList) {
            m = /^path-([0-9]+)$/.exec(itsclass);
            if (m) {
                item_id = m[1];
                break;
            }
       }
       item_path = event_source.target.textContent;

       if (clicks == 1) {
           single_click_callback.call(self, item_id, item_path);
       } else {
           double_click_callback.call(self, item_id, item_path);
       }
       clicks = 0;
    }

    function sdc_inner(event) {
      event_source = event;
      clicks++;
      if (clicks == 1) {
          setTimeout(sdc_timer, timeout || 300);
      }
    }

    jQuery(this).click(sdc_inner);
  }
  return this.each(sdc_outer);
}

function single_click_callback(item_id, item_path) {
    // open in browser or at least via browser
    var win = window.open('items/' + item_path, '_blank');
}

function double_click_callback(item_id, item_path) {
    jQuery.get('items-native/' + item_path);
}

// ---------- New List Maintenance --------------------------------------------------

function confirm_new_remove(item_id) {
    var path = $(`.path-${item_id}`)[0].textContent;
    if (confirm(`Remove ${path} from new list?`)) {
        jQuery.get(`/new-remove?item_id=${item_id}`);
    }
    // remove from GUI
    $(`#new-indicator-${item_id}`)[0].remove();
    update_new_indicator();
}

function new_indicator_click() {
    // is shift depressed, then user just wants to reset the indicator, else run a search for new items
    if (event.shiftKey) {
        jQuery.get('new-reset');
        update_new_indicator();
    } else {
        do_main_search(true);
        update_new_indicator();
    }
}


// ---------- Handle New Indicator and other dynamic stuff --------------------------

function update_new_indicator() {

    function update_new_indicator_cb(data) {

        const classes = $('#new-indicator')[0].classList;
        if (data == 'hot') {
            classes.remove('new-indicator-cold');
            classes.remove('new-indicator-none');
            classes.add('new-indicator-hot');
        }
        else if (data == 'cold') {
            classes.add('new-indicator-cold');
            classes.remove('new-indicator-none');
            classes.remove('new-indicator-hot');
        }
        else {
            classes.remove('new-indicator-cold');
            classes.add('new-indicator-none');
            classes.remove('new-indicator-hot');
        }
    }

    jQuery.get('/new', update_new_indicator_cb)

}


function periodic_tasks() {
    update_new_indicator();
}

setInterval(periodic_tasks, refresh_interval*1000);
// run right away too
periodic_tasks();


/* ---------- Notes for reference --------------------------
  modifying element class
  document.getElementById(menu_state).style = 'display:none';
  var classparts = document.getElementById(menu_link).classList;
  classparts.remove('active');
  document.getElementById(menu_link).classList = classparts;
*/

     