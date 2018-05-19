// Hack used to prevent typing into non-React elements (e.g. a select2 box) from triggering keyboard
// events on React elements (e.g. the clip viewer). This happens because React uses a synthetic event
// system separate from the one built-in to the DOM, so it's difficult to deal with the cross-system
// triggers. We use this global variable for any time when there should definitely be no keypress
// events happening EXCEPT on the element the user is currently typing into.


class KeyboardManager {
  _lock_count = 0;
  modifiers = new Set();

  constructor() {
    document.addEventListener('keydown', this._onKeyDown);
    document.addEventListener('keyup', this._onKeyUp);
  }

  locked = () => {
    return this._lock_count > 0;
  }

  lock = () => {
    this._lock_count += 1;
  }

  unlock = () => {
    this._lock_count -= 1;
    console.assert(this._lock_count >= 0);
  }

  _onKeyDown = (e) => {
    if (e.shiftKey) {
      this.modifiers.add('shift');
    }

    this.modifiers.add(String.fromCharCode(e.which));
  }

  _onKeyUp = (e) => {
    if (!e.shiftKey) {
      this.modifiers.delete('shift');
    }

    this.modifiers.delete(String.fromCharCode(e.which));
  }
}

export default new KeyboardManager();
