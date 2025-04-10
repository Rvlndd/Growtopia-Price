import { checkItemPrice } from './price.js';

(async () => {
    try {
        const data = await checkItemPrice("rayman");
        console.log(data);
    } catch (err) {
        console.error("fail:", err.message);
    }
})();
