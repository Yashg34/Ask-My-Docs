const jwt = require('jsonwebtoken');

const authMiddleware = (req, res, next) => {
    const token = req.cookies?.token; 

    if (!token) {
        return res.status(401).json({ error: { code: 401, message: 'Access denied. No token provided in cookies.' } });
    }

    try {
        const decoded = jwt.verify(token, process.env.JWT_SECRET);
        req.user = decoded;
        next();
    } catch (error) {
        res.status(401).json({ error: { code: 401, message: 'Invalid or expired token.' } });
    }
};

module.exports = authMiddleware;